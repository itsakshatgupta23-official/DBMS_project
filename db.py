"""
db.py – Centralized Query & Connection Manager with Connection Pooling.
Uses MySQLConnectionPool (pool_size=5) to avoid per-request connection overhead.
Connects to Aiven for MySQL over SSL (port 26320).
"""

import os
import time
import json
import threading

import mysql.connector
import mysql.connector.pooling
from flask import g, session, request, has_request_context

from config import Config

_local = threading.local()

# ──────────────────────────────────────────────────────────────
# Connection Pool – created once at module import time
# ──────────────────────────────────────────────────────────────

def _get_connection_params():
    return dict(
        host=os.getenv("DB_HOST", Config.DB_HOST),
        port=int(os.getenv("DB_PORT", Config.DB_PORT)),
        user=os.getenv("DB_USER", Config.DB_USER),
        password=os.getenv("DB_PASSWORD", Config.DB_PASSWORD),
        database=os.getenv("DB_NAME", Config.DB_NAME),
        connection_timeout=15,
        autocommit=True,
        ssl_disabled=False,  # Aiven requires SSL
    )


def _create_pool():
    """Create a new MySQLConnectionPool.  Returns pool or None on failure."""
    try:
        params = _get_connection_params()
        return mysql.connector.pooling.MySQLConnectionPool(
            pool_name="chronicle",
            pool_size=5,
            pool_reset_session=True,
            **params,
        )
    except Exception as exc:
        print(f"[db] Warning: could not create connection pool: {exc}")
        return None


_pool = _create_pool()
_pool_lock = threading.Lock()


def _get_pooled_connection():
    """Return a connection from the pool, rebuilding pool if needed."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = _create_pool()
    if _pool is not None:
        try:
            return _pool.get_connection()
        except mysql.connector.errors.PoolExhausted:
            pass  # Fall through to direct connect
        except Exception:
            pass
    # Fallback: direct connection when pool unavailable / exhausted
    return mysql.connector.connect(**_get_connection_params())


# ──────────────────────────────────────────────────────────────
# Request-scoped connection management
# ──────────────────────────────────────────────────────────────

def get_db():
    """
    Get or create the MySQL connection for the current Flask request.
    Reuses g.db across the request lifecycle; returns from pool on first call.
    """
    if has_request_context():
        if "db" not in g or g.db is None or not g.db.is_connected():
            g.db = _get_pooled_connection()
        return g.db

    # Outside request context (CLI scripts, background tasks)
    conn = getattr(_local, "conn", None)
    if conn is None or not conn.is_connected():
        conn = _get_pooled_connection()
        _local.conn = conn
    return conn


def close_db(e=None):
    """
    Return the database connection to the pool on request teardown.
    Registered via app.teardown_appcontext(close_db).
    Calling .close() on a pooled connection returns it to the pool.
    """
    if has_request_context():
        db_conn = g.pop("db", None)
        if db_conn is not None:
            try:
                db_conn.close()  # Returns to pool (does not physically close)
            except Exception:
                pass
    else:
        conn = getattr(_local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            _local.conn = None


def get_connection():
    """Return the active connection (for explicit transaction control)."""
    return get_db()


def commit(conn=None):
    target = conn or get_db()
    if target and target.is_connected():
        target.commit()


def rollback(conn=None):
    target = conn or get_db()
    if target and target.is_connected():
        target.rollback()


def cleanup_sleeping_connections():
    """
    Kills any orphaned 'Sleep' connections for our user.
    Skipped on Aiven (ssl_disabled=False) as Aiven manages connections natively.
    """
    params = _get_connection_params()
    # Aiven uses SSL and manages connections itself — skip KILL routine
    if not params.get("ssl_disabled", True):
        return
    target_user = params.get("user", "")
    try:
        conn = mysql.connector.connect(**params)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SHOW PROCESSLIST")
        processes = cursor.fetchall()
        for proc in processes:
            if proc.get("Command") == "Sleep" and proc.get("User") == target_user:
                try:
                    cursor.execute(f"KILL {proc['Id']}")
                    print(f"[Cleanup] Killed orphaned sleeping process ID: {proc['Id']}")
                except Exception:
                    pass
        cursor.close()
        conn.close()
    except Exception as err:
        print(f"[Cleanup Warning] Could not perform process cleanup: {err}")


# ──────────────────────────────────────────────────────────────
# Schema bootstrap
# ──────────────────────────────────────────────────────────────

def init_db():
    """Execute database/schema.sql against the DB (idempotent)."""
    schema_path = os.path.join(os.path.dirname(__file__), "database", "schema.sql")
    if not os.path.exists(schema_path):
        return
    with open(schema_path, "r", encoding="utf-8") as f:
        sql_script = f.read()

    clean_lines = [
        line for line in sql_script.splitlines()
        if not line.strip().startswith("--") and not line.strip().startswith("#")
    ]
    statements = [s.strip() for s in "\n".join(clean_lines).split(";") if s.strip()]

    conn = get_db()
    cursor = conn.cursor()
    try:
        for stmt in statements:
            cursor.execute(stmt)
        conn.commit()
    finally:
        cursor.close()


# ──────────────────────────────────────────────────────────────
# Log writer (reuses active connection, never creates connection leaks)
# ──────────────────────────────────────────────────────────────

def _mask_params(params):
    """Return a JSON-safe, masked representation of query parameters."""
    if params is None:
        return None
    if isinstance(params, (list, tuple)):
        masked = ["***" if i in (1, 2) else str(v) for i, v in enumerate(params)]
        return json.dumps(masked)
    return json.dumps(str(params))


def _write_log(user_id, action_label, query_type, sql_text,
               params, status, error_message, rows_affected, duration_ms, route):
    # Prevent recursion when logging query_log operations
    if "query_log" in sql_text.lower():
        return
    try:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO query_log
                    (user_id, action_label, query_type, sql_text, params_json,
                     status, error_message, rows_affected, duration_ms, route)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    user_id,
                    action_label,
                    query_type,
                    sql_text[:4000],
                    _mask_params(params),
                    status,
                    error_message[:2000] if error_message else None,
                    rows_affected,
                    duration_ms,
                    route,
                ),
            )
        finally:
            cur.close()
    except Exception:
        pass  # Never let logging crash the main application


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

def run_query(sql: str, params=None, action_label: str = "QUERY",
              fetch: str = "all", conn=None):
    """
    Execute *sql* with *params* on the active connection and log metadata.

    Parameters
    ----------
    sql          : Raw SQL string (use %s placeholders).
    params       : Tuple / list of bind values.
    action_label : Human-readable label for query_log.
    fetch        : "all" | "one" | "none"
    conn         : Pass an explicit connection for transaction management.

    Returns
    -------
    For SELECT queries → list-of-dicts (fetch="all") or dict / None (fetch="one").
    For DML queries    → rows_affected (int).
    """
    use_conn = conn if conn is not None else get_db()
    cursor = use_conn.cursor(dictionary=True, buffered=True)

    user_id  = session.get("user_id") if has_request_context() and "user_id" in session else None
    route    = request.path if has_request_context() else None
    sql_text = sql.strip()
    q_type   = sql_text.split()[0].upper() if sql_text else "UNKNOWN"

    start = time.perf_counter()
    status = "SUCCESS"
    error_msg = None
    rows = 0
    result = None

    try:
        cursor.execute(sql_text, params or ())
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        if cursor.lastrowid:
            if has_request_context():
                g.last_insert_id = cursor.lastrowid
            else:
                _local.last_insert_id = cursor.lastrowid

        if fetch == "lastrowid":
            result = cursor.lastrowid
        elif fetch == "all":
            result = cursor.fetchall()
            rows = len(result)
        elif fetch == "one":
            result = cursor.fetchone()
            try:
                while cursor.fetchone() is not None:
                    pass
            except Exception:
                pass
            rows = 1 if result else 0
        else:
            rows = cursor.rowcount
            result = rows

    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        status = "FAILED"
        error_msg = str(exc)
        result = None
        raise
    finally:
        cursor.close()
        _write_log(user_id, action_label, q_type, sql_text,
                   params, status, error_msg, rows, elapsed_ms, route)

    return result


def get_last_insert_id():
    """Return the last inserted auto-increment ID from the most recent INSERT run_query."""
    if has_request_context():
        return getattr(g, "last_insert_id", None)
    return getattr(_local, "last_insert_id", None)

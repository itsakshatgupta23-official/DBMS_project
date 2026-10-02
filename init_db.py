"""
init_db.py – One-shot script to push schema + seed data to remote MySQL.
Supports Aiven for MySQL (SSL) and standard MySQL.
Run locally ONCE: python init_db.py [--seed] [--indexes]
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import mysql.connector
from config import Config

SCHEMA_FILE  = "database/schema.sql"
VIEWS_FILE   = "database/views.sql"
INDEXES_FILE = "database/indexes.sql"
SEED_FILE    = "database/seed.sql"


def run_sql_file(conn, filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        script = f.read()
    cursor = conn.cursor()
    # Filter comment lines before splitting on semicolons
    clean_lines = [
        line for line in script.splitlines()
        if not line.strip().startswith("--") and not line.strip().startswith("#")
    ]
    clean_script = "\n".join(clean_lines)
    statements = [s.strip() for s in clean_script.split(";") if s.strip()]
    for stmt in statements:
        try:
            cursor.execute(stmt)
        except mysql.connector.Error as e:
            # Duplicate entry / duplicate index on seed/indexes is acceptable
            if e.errno not in (1062, 1050, 1060, 1061):
                print(f"  [WARN] {e}")
    conn.commit()
    cursor.close()


if __name__ == "__main__":
    run_seed    = "--seed"    in sys.argv
    run_indexes = "--indexes" in sys.argv or True  # always run indexes by default

    # Aiven requires SSL; also works with plain MySQL
    connect_kwargs = dict(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        autocommit=False,
        connection_timeout=20,
        ssl_disabled=False,
    )

    print(f"Connecting to {Config.DB_HOST}:{Config.DB_PORT} ...")
    try:
        # Try connecting without a DB first (to CREATE DATABASE if possible)
        conn = mysql.connector.connect(**connect_kwargs)
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{Config.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.execute(f"USE `{Config.DB_NAME}`")
        cursor.close()
        print(f"[OK] Using database: {Config.DB_NAME}\n")
    except mysql.connector.Error:
        # Fallback: connect directly (Aiven pre-creates defaultdb)
        conn = mysql.connector.connect(**{**connect_kwargs, "database": Config.DB_NAME})
        print(f"[OK] Connected directly to database: {Config.DB_NAME}\n")

    print(f"Running {SCHEMA_FILE} ...")
    run_sql_file(conn, SCHEMA_FILE)
    print("[OK] Schema applied.\n")

    print(f"Running {VIEWS_FILE} ...")
    run_sql_file(conn, VIEWS_FILE)
    print("[OK] Views created.\n")

    print(f"Running {INDEXES_FILE} ...")
    run_sql_file(conn, INDEXES_FILE)
    print("[OK] Performance indexes created.\n")

    if run_seed:
        print(f"Running {SEED_FILE} ...")
        run_sql_file(conn, SEED_FILE)
        print("[OK] Seed data inserted.\n")
    else:
        print("[INFO] Skipping seed data. Pass --seed to include demo data.\n")

    conn.close()
    print("[OK] Database initialisation complete!")

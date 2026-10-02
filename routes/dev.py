"""
routes/dev.py – Developer SQL Log Viewer + EXPLAIN executor
Access is restricted to users with is_developer = TRUE.
"""

from flask import Blueprint, render_template, request, jsonify, abort
import db
from utils.decorators import login_required, dev_required

dev_bp = Blueprint("dev", __name__, url_prefix="/dev")


@dev_bp.route("/sql-log")
@login_required
@dev_required
def sql_log():
    """
    SQL log viewer with filters:
      - status  : SUCCESS | FAILED
      - q_type  : SELECT | INSERT | UPDATE | DELETE | …
      - route   : free-text match
      - action  : free-text match
      - limit   : 25 | 50 | 100 | 200
    """
    status_filter = request.args.get("status", "")
    qtype_filter  = request.args.get("q_type", "")
    route_filter  = request.args.get("route", "")
    action_filter = request.args.get("action", "")
    limit         = min(int(request.args.get("limit", 50)), 500)

    conditions = []
    params     = []

    if status_filter:
        conditions.append("status = %s")
        params.append(status_filter)
    if qtype_filter:
        conditions.append("query_type = %s")
        params.append(qtype_filter)
    if route_filter:
        conditions.append("route LIKE %s")
        params.append(f"%{route_filter}%")
    if action_filter:
        conditions.append("action_label LIKE %s")
        params.append(f"%{action_filter}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    logs = db.run_query(
        f"""
        SELECT ql.log_id, ql.user_id, u.username, ql.action_label,
               ql.query_type, ql.sql_text, ql.params_json,
               ql.status, ql.error_message, ql.rows_affected,
               ql.duration_ms, ql.route, ql.created_at
        FROM   query_log ql
        LEFT JOIN users u ON u.user_id = ql.user_id
        {where}
        ORDER  BY ql.created_at DESC
        LIMIT  %s
        """,
        tuple(params),
        action_label="DEV_FETCH_LOGS",
        fetch="all",
    )

    # Aggregate stats
    stats = db.run_query(
        """
        SELECT
            COUNT(*)                                     AS total,
            SUM(status = 'SUCCESS')                      AS success_count,
            SUM(status = 'FAILED')                       AS fail_count,
            ROUND(AVG(duration_ms), 2)                   AS avg_ms,
            MAX(duration_ms)                              AS max_ms
        FROM query_log
        """,
        action_label="DEV_LOG_STATS",
        fetch="one",
    )

    return render_template(
        "dev/sql_log.html",
        logs=logs,
        stats=stats,
        filters=dict(
            status=status_filter, q_type=qtype_filter,
            route=route_filter, action=action_filter, limit=limit
        ),
    )


@dev_bp.route("/explain", methods=["POST"])
@login_required
@dev_required
def explain():
    """Run EXPLAIN on a submitted SQL statement and return JSON."""
    data = request.get_json(silent=True) or {}
    sql  = data.get("sql", "").strip()
    if not sql:
        return jsonify({"error": "No SQL provided"}), 400
    if not sql.upper().startswith("SELECT"):
        return jsonify({"error": "Only SELECT statements are allowed for EXPLAIN"}), 400

    try:
        rows = db.run_query(
            f"EXPLAIN {sql}",
            action_label="DEV_EXPLAIN",
            fetch="all",
        )
        return jsonify({"rows": rows})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

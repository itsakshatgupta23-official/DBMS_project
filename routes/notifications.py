"""routes/notifications.py – Notification list and mark-read"""
from flask import Blueprint, render_template, jsonify, session
import db
from utils.decorators import login_required

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")

@notifications_bp.route("/")
@login_required
def list_notifications():
    user_id = session["user_id"]
    notifs = db.run_query(
        "SELECT notif_id, user_id, message, is_read, created_at FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT 100",
        (user_id,), action_label="FETCH_NOTIFS", fetch="all"
    )
    db.run_query("UPDATE notifications SET is_read=TRUE WHERE user_id=%s", (user_id,), action_label="MARK_READ", fetch="none")
    db.commit()
    return render_template("notifications.html", notifications=notifs)

@notifications_bp.route("/count")
@login_required
def notif_count():
    user_id = session["user_id"]
    row = db.run_query("SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE", (user_id,), action_label="NOTIF_COUNT", fetch="one")
    return jsonify({"count": row["cnt"] if row else 0})

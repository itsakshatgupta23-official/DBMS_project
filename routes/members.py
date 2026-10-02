"""routes/members.py – Join request approvals, member management"""
from flask import Blueprint, request, redirect, url_for, session, jsonify, abort
import db
from utils.decorators import login_required, host_required, space_member_required

members_bp = Blueprint("members", __name__, url_prefix="/spaces/<int:space_id>/members")

@members_bp.route("/requests")
@login_required
@host_required
def join_requests(space_id):
    reqs = db.run_query(
        """SELECT jr.request_id, jr.status, jr.requested_at, u.username, u.user_id
           FROM join_requests jr JOIN users u ON u.user_id=jr.user_id
           WHERE jr.space_id=%s AND jr.status='PENDING' ORDER BY jr.requested_at""",
        (space_id,), action_label="FETCH_JOIN_REQS", fetch="all"
    )
    from flask import render_template
    return render_template("space/modals/join_requests.html", requests=reqs, space_id=space_id)

@members_bp.route("/requests/<int:req_id>/decide", methods=["POST"])
@login_required
@host_required
def decide_request(space_id, req_id):
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    raw_status = (data.get("status") or data.get("action") or "").strip().upper()

    if raw_status in ("APPROVE", "APPROVED"):
        status = "APPROVED"
    elif raw_status in ("REJECT", "REJECTED"):
        status = "REJECTED"
    else:
        return jsonify({"success": False, "error": "Invalid action. Must be approve or reject."}), 400

    req = db.run_query("SELECT * FROM join_requests WHERE request_id=%s AND space_id=%s",(req_id, space_id), fetch="one", action_label="FETCH_REQ")
    if not req:
        return jsonify({"success": False, "error": "Request not found"}), 404

    db.run_query(
        "UPDATE join_requests SET status=%s, decided_at=NOW(), decided_by=%s WHERE request_id=%s",
        (status, session["user_id"], req_id), action_label="DECIDE_REQ", fetch="none"
    )
    if status == "APPROVED":
        db.run_query(
            "INSERT IGNORE INTO space_members (space_id, user_id) VALUES (%s,%s)",
            (space_id, req["user_id"]), action_label="ADD_MEMBER", fetch="none"
        )
    space = db.run_query("SELECT name FROM spaces WHERE space_id=%s",(space_id,),fetch="one",action_label="SPACE_NAME")
    msg = f"Your request to join '{space['name']}' was {status.lower()}."
    db.run_query("INSERT INTO notifications (user_id, message) VALUES (%s,%s)",(req["user_id"], msg), action_label="NOTIFY_REQ_RESULT", fetch="none")
    db.commit()
    return jsonify({"success": True, "message": f"Request {status.lower()}."})

@members_bp.route("/<int:target_user_id>/remove", methods=["POST"])
@login_required
@host_required
def remove_member(space_id, target_user_id):
    if target_user_id == session["user_id"]:
        return jsonify({"error":"Host cannot remove themselves."}), 400
    db.run_query(
        "DELETE FROM space_members WHERE space_id=%s AND user_id=%s AND role='MEMBER'",
        (space_id, target_user_id), action_label="REMOVE_MEMBER", fetch="none"
    )
    db.commit()
    return jsonify({"message":"Member removed."})

"""routes/spaces.py – Space management (Phase 2)"""
import random, string
import mysql.connector
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, abort
import db
from utils.decorators import login_required, space_member_required, host_required

spaces_bp = Blueprint("spaces", __name__, url_prefix="/spaces")

def _gen_invite_code(length=6):
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(chars, k=length))
        existing = db.run_query("SELECT 1 FROM spaces WHERE invite_code = %s", (code,), fetch="one", action_label="CHECK_INVITE_CODE")
        if not existing:
            return code

@spaces_bp.route("/create-modal")
@login_required
def create_modal():
    return render_template("space/modals/create_space.html")

@spaces_bp.route("/create", methods=["POST"])
@spaces_bp.route("", methods=["POST"])
@spaces_bp.route("/", methods=["POST"])
@login_required
def create_space():
    try:
        user_id = session.get("user_id")

        # Verify that session['user_id'] actually exists in users table on Aiven
        user = db.run_query(
            "SELECT user_id FROM users WHERE user_id = %s",
            (user_id,),
            action_label="VERIFY_USER_EXISTS",
            fetch="one",
        )
        if not user:
            session.clear()  # Clear invalid session
            return jsonify({'success': False, 'error': 'Session expired or invalid user. Please log in again.'}), 401

        data = request.get_json(silent=True) or request.form.to_dict() or {}
        name = (data.get("name") or "").strip()
        description = (data.get("description") or "").strip()
        space_type = (data.get("space_type") or "Other").strip()

        if not name:
            return jsonify({"success": False, "error": "Space name is required"}), 400

        code = _gen_invite_code()
        db.run_query(
            "INSERT INTO spaces (name, description, space_type, invite_code, host_id) VALUES (%s,%s,%s,%s,%s)",
            (name, description, space_type, code, user_id),
            action_label="CREATE_SPACE", fetch="none"
        )
        db.commit()

        space = db.run_query(
            "SELECT space_id FROM spaces WHERE invite_code=%s", (code,),
            fetch="one", action_label="FETCH_NEW_SPACE"
        )
        if not space:
            return jsonify({"success": False, "error": "Failed to retrieve created space."}), 500

        space_id = space["space_id"]
        db.run_query(
            "INSERT INTO space_members (space_id, user_id, role) VALUES (%s,%s,'HOST')",
            (space_id, user_id), action_label="ADD_HOST_MEMBER", fetch="none"
        )
        db.commit()

        redirect_url = url_for("spaces.space_home", space_id=space_id)
        return jsonify({
            "success": True,
            "redirect_url": redirect_url,
            "redirect": redirect_url,
            "space_id": space_id,
            "message": "Space created successfully."
        }), 201
    except mysql.connector.Error as err:
        db.rollback()
        # If foreign key constraint failure (1452) occurs, clear invalid session
        if getattr(err, 'errno', None) == 1452 or '1452' in str(err):
            session.clear()
            return jsonify({'success': False, 'error': 'Session expired or invalid user. Please log in again.'}), 401
        return jsonify({'success': False, 'error': str(err)}), 500
    except Exception as e:
        db.rollback()
        if '1452' in str(e):
            session.clear()
            return jsonify({'success': False, 'error': 'Session expired or invalid user. Please log in again.'}), 401
        return jsonify({'success': False, 'error': str(e)}), 500

@spaces_bp.route("/join-modal")
@login_required
def join_modal():
    return render_template("space/modals/join_space.html")

@spaces_bp.route("/join", methods=["POST"])
@login_required
def join_space():
    try:
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        code = (data.get("invite_code") or "").strip().upper()
        user_id = session.get("user_id")

        if not code:
            return jsonify({"success": False, "error": "Invite code is required."}), 400

        space = db.run_query("SELECT * FROM spaces WHERE invite_code=%s", (code,), fetch="one", action_label="JOIN_FIND_SPACE")
        if not space:
            return jsonify({"success": False, "error": "Invalid invite code."}), 404

        space_id = space["space_id"]
        already = db.run_query("SELECT 1 FROM space_members WHERE space_id=%s AND user_id=%s", (space_id, user_id), fetch="one", action_label="JOIN_CHECK_MEMBER")
        if already:
            redirect_url = url_for("spaces.space_home", space_id=space_id)
            return jsonify({"success": True, "redirect": redirect_url, "redirect_url": redirect_url})

        pending = db.run_query("SELECT 1 FROM join_requests WHERE space_id=%s AND user_id=%s AND status='PENDING'", (space_id, user_id), fetch="one", action_label="JOIN_CHECK_PENDING")
        if pending:
            return jsonify({"success": True, "message": "Join request already pending."})

        db.run_query(
            "INSERT INTO join_requests (space_id, user_id) VALUES (%s,%s)",
            (space_id, user_id), action_label="JOIN_INSERT_REQ", fetch="none"
        )
        db.commit()
        db.run_query(
            "INSERT INTO notifications (user_id, message) VALUES (%s, %s)",
            (space["host_id"], f"{session['username']} wants to join '{space['name']}'."),
            action_label="JOIN_NOTIFY_HOST", fetch="none"
        )
        db.commit()
        return jsonify({"success": True, "message": "Join request sent! Waiting for host approval."})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@spaces_bp.route("/<int:space_id>")
@login_required
@space_member_required
def space_home(space_id):
    space = db.run_query("SELECT * FROM spaces WHERE space_id=%s",(space_id,), fetch="one", action_label="SPACE_HOME_FETCH")
    if not space: abort(404)
    role = db.run_query("SELECT role FROM space_members WHERE space_id=%s AND user_id=%s",(space_id, session["user_id"]), fetch="one", action_label="SPACE_ROLE_FETCH")
    members = db.run_query(
        "SELECT u.user_id, u.username, sm.role, sm.joined_at FROM space_members sm JOIN users u ON u.user_id=sm.user_id WHERE sm.space_id=%s ORDER BY sm.role DESC, u.username",
        (space_id,), action_label="SPACE_MEMBERS", fetch="all"
    )
    return render_template("space/home.html", space=space, role=role["role"] if role else "MEMBER", members=members)

@spaces_bp.route("/requests/<int:request_id>/decide", methods=["POST"])
@login_required
def decide_request(request_id):
    """Host decision on a pending join request."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    raw_status = (data.get("status") or data.get("action") or "").strip().upper()

    if raw_status in ("APPROVE", "APPROVED"):
        status = "APPROVED"
    elif raw_status in ("REJECT", "REJECTED"):
        status = "REJECTED"
    else:
        return jsonify({"success": False, "error": "Invalid decision status. Must be APPROVED or REJECTED."}), 400

    req = db.run_query(
        "SELECT * FROM join_requests WHERE request_id = %s",
        (request_id,),
        fetch="one",
        action_label="FETCH_JOIN_REQ_DECIDE"
    )
    if not req:
        return jsonify({"success": False, "error": "Join request not found."}), 404

    space_id = req["space_id"]
    # Verify current user is HOST of this space
    is_host = db.run_query(
        "SELECT 1 FROM space_members WHERE space_id = %s AND user_id = %s AND role = 'HOST'",
        (space_id, session["user_id"]),
        fetch="one",
        action_label="CHECK_HOST_DECIDE"
    )
    if not is_host:
        return jsonify({"success": False, "error": "Unauthorized: Only space host can decide join requests."}), 403

    db.run_query(
        "UPDATE join_requests SET status = %s, decided_at = NOW(), decided_by = %s WHERE request_id = %s",
        (status, session["user_id"], request_id),
        action_label="UPDATE_JOIN_REQ_DECIDE",
        fetch="none"
    )

    if status == "APPROVED":
        db.run_query(
            "INSERT IGNORE INTO space_members (space_id, user_id) VALUES (%s, %s)",
            (space_id, req["user_id"]),
            action_label="ADD_MEMBER_APPROVED",
            fetch="none"
        )

    space = db.run_query("SELECT name FROM spaces WHERE space_id = %s", (space_id,), fetch="one", action_label="FETCH_SPACE_NAME")
    space_name = space["name"] if space else "the space"
    msg = f"Your request to join '{space_name}' was {status.lower()}."
    db.run_query(
        "INSERT INTO notifications (user_id, message) VALUES (%s, %s)",
        (req["user_id"], msg),
        action_label="NOTIFY_JOIN_DECISION",
        fetch="none"
    )
    db.commit()

    return jsonify({
        "success": True,
        "message": f"Request {status.lower()}.",
        "space_id": space_id
    })

@spaces_bp.route("/<int:space_id>/badge-counts", methods=["GET"])
@login_required
@space_member_required
def get_space_badge_counts(space_id):
    """Return JSON counts of pending requests and unread items for space sidebar."""
    user_id = session["user_id"]

    # 1. Count pending join requests (only if current user is HOST)
    is_host = db.run_query(
        "SELECT 1 FROM space_members WHERE space_id = %s AND user_id = %s AND role = 'HOST'",
        (space_id, user_id),
        fetch="one",
        action_label="CHECK_HOST_BADGES"
    )
    pending_requests_count = 0
    if is_host:
        cnt = db.run_query(
            "SELECT COUNT(*) AS count FROM join_requests WHERE space_id = %s AND status = 'PENDING'",
            (space_id,),
            fetch="one",
            action_label="COUNT_PENDING_REQS"
        )
        pending_requests_count = cnt["count"] if cnt else 0

    return jsonify({
        "pending_requests": pending_requests_count,
        "unread_chats": 0
    })


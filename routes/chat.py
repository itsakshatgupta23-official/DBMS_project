"""routes/chat.py – Group chat & private 1-on-1 conversations"""
from flask import Blueprint, render_template, request, session, jsonify, abort
import db
from utils.decorators import login_required, space_member_required

from utils.cloudinary_helper import upload_file

chat_bp = Blueprint("chat", __name__, url_prefix="/spaces/<int:space_id>")
messages_bp = Blueprint("messages", __name__)


def _do_pin_to_notes(message_id):
    try:
        # 1. Mark message as pinned in chat_messages
        db.run_query(
            "UPDATE chat_messages SET is_pinned = 1 WHERE message_id = %s",
            (message_id,), fetch="none", action_label="PIN_MSG"
        )
        db.commit()

        # 2. Retrieve message details
        msg = db.run_query(
            """SELECT cm.space_id, cm.sender_id, cm.message, cm.file_url, cm.original_filename, u.username AS sender
               FROM chat_messages cm
               JOIN users u ON u.user_id = cm.sender_id
               WHERE cm.message_id = %s""",
            (message_id,), fetch="one", action_label="GET_PIN_MSG"
        )
        if not msg:
            return jsonify({'success': False, 'error': 'Message not found'}), 404

        # 3. Insert into notes
        note_content = (msg.get('message') or '').strip()
        if not note_content:
            note_content = 'Attached File'
        if msg.get('file_url'):
            fname = msg.get('original_filename') or 'Attachment'
            note_content += f"\n\n[{fname}]({msg['file_url']})"

        db.run_query(
            """INSERT INTO notes (space_id, created_by, title, content, source_message_id) 
               VALUES (%s, %s, %s, %s, %s)""",
            (msg['space_id'], session['user_id'], 'Pinned Chat Note', note_content, message_id),
            fetch="none", action_label="PIN_TO_NOTES_INSERT"
        )
        db.commit()

        return jsonify({'success': True, 'message': 'Pinned and saved to Notes!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@messages_bp.route("/messages/<int:message_id>/pin-to-notes", methods=["POST"])
@login_required
def pin_to_notes_global(message_id):
    return _do_pin_to_notes(message_id)


@chat_bp.route("/messages/<int:message_id>/pin-to-notes", methods=["POST"])
@login_required
def pin_to_notes_space(space_id, message_id):
    return _do_pin_to_notes(message_id)


@messages_bp.route("/delete-chat/<int:chat_id>", methods=["POST", "DELETE"])
@login_required
def delete_chat(chat_id):
    user_id = session["user_id"]

    # 1. Check in chat_messages (group chat)
    msg = db.run_query(
        "SELECT message_id, space_id, sender_id FROM chat_messages WHERE message_id = %s",
        (chat_id,), fetch="one", action_label="FETCH_CHAT_FOR_DELETE"
    )
    if msg:
        is_host = db.run_query(
            "SELECT 1 FROM space_members WHERE space_id = %s AND user_id = %s AND role = 'HOST'",
            (msg["space_id"], user_id), fetch="one", action_label="CHECK_HOST_DELETE_CHAT"
        )
        if msg["sender_id"] != user_id and not is_host:
            return jsonify({"success": False, "error": "Unauthorized to delete this message."}), 403

        db.run_query(
            "DELETE FROM chat_messages WHERE message_id = %s",
            (chat_id,), fetch="none", action_label="DELETE_CHAT_MSG"
        )
        db.commit()
        return jsonify({"success": True, "message": "Message deleted successfully."})

    # 2. Check in private_messages
    pmsg = db.run_query(
        "SELECT message_id, sender_id FROM private_messages WHERE message_id = %s",
        (chat_id,), fetch="one", action_label="FETCH_PRIV_FOR_DELETE"
    )
    if pmsg:
        if pmsg["sender_id"] != user_id:
            return jsonify({"success": False, "error": "Unauthorized to delete this message."}), 403

        db.run_query(
            "DELETE FROM private_messages WHERE message_id = %s",
            (chat_id,), fetch="none", action_label="DELETE_PRIV_MSG"
        )
        db.commit()
        return jsonify({"success": True, "message": "Message deleted successfully."})

    return jsonify({"success": False, "error": "Message not found."}), 404


# ── Group Chat ──────────────────────────────────────────────

@chat_bp.route("/chat")
@login_required
@space_member_required
def group_chat(space_id):
    # Mark unread chat messages as read for this user
    db.run_query(
        "UPDATE chat_messages SET is_read = TRUE WHERE space_id = %s AND sender_id != %s AND is_read = FALSE",
        (space_id, session["user_id"]), fetch="none", action_label="MARK_CHAT_READ"
    )
    db.commit()

    space = db.run_query("SELECT space_id, name, description, space_type, invite_code FROM spaces WHERE space_id=%s", (space_id,), fetch="one", action_label="CHAT_SPACE")
    messages = db.run_query(
        """SELECT cm.message_id, cm.message, cm.created_at, cm.file_url, cm.file_type, cm.original_filename, cm.is_pinned,
                  u.username AS sender,
                  (cm.sender_id=%s) AS is_mine
           FROM chat_messages cm JOIN users u ON u.user_id=cm.sender_id
           WHERE cm.space_id=%s ORDER BY cm.created_at ASC LIMIT 200""",
        (session["user_id"], space_id), action_label="GROUP_CHAT_FETCH", fetch="all"
    )
    members = db.run_query(
        "SELECT u.user_id, u.username FROM space_members sm JOIN users u ON u.user_id=sm.user_id WHERE sm.space_id=%s AND sm.user_id!=%s",
        (space_id, session["user_id"]), action_label="CHAT_MEMBERS", fetch="all"
    )
    role = db.run_query("SELECT role FROM space_members WHERE space_id=%s AND user_id=%s", (space_id, session["user_id"]), fetch="one", action_label="CHAT_ROLE")
    return render_template("space/chat.html", space=space, messages=messages,
                           members=members, role=role["role"] if role else "MEMBER")

@chat_bp.route("/chat/send", methods=["POST"])
@login_required
@space_member_required
def send_group_message(space_id):
    if request.is_json:
        data = request.get_json(silent=True) or {}
        msg = data.get("message", "").strip()
        f = None
    else:
        msg = request.form.get("message", "").strip()
        f = request.files.get("file")

    file_url = None
    file_type = None
    orig_filename = None

    if f and f.filename:
        orig_filename = f.filename
        try:
            result = upload_file(f, folder=f"chronicle/{space_id}/chat")
            file_url = result["secure_url"]
            ext = f.filename.rsplit(".", 1)[1].lower() if "." in f.filename else "file"
            file_type = result.get("format") or ext
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"Upload failed: {e}"}), 500

    if not msg and not file_url:
        return jsonify({"error": "Empty message"}), 400

    db.run_query(
        """INSERT INTO chat_messages (space_id, sender_id, message, file_url, file_type, original_filename, is_pinned)
           VALUES (%s, %s, %s, %s, %s, %s, 0)""",
        (space_id, session["user_id"], msg, file_url, file_type, orig_filename),
        action_label="SEND_GROUP_MSG", fetch="none"
    )
    db.commit()
    msg_id = db.get_last_insert_id()
    if not msg_id:
        fallback = db.run_query(
            "SELECT MAX(message_id) AS id FROM chat_messages WHERE space_id=%s AND sender_id=%s",
            (space_id, session["user_id"]), fetch="one", action_label="FALLBACK_MSG_ID"
        )
        msg_id = fallback["id"] if fallback else None

    return jsonify({"message_obj": {
        "message_id": msg_id,
        "message": msg,
        "sender": session["username"],
        "is_mine": True,
        "time": "just now",
        "file_url": file_url,
        "file_type": file_type,
        "original_filename": orig_filename,
        "is_pinned": False,
    }})

@chat_bp.route("/chat/poll")
@login_required
@space_member_required
def poll_group(space_id):
    after = int(request.args.get("after", 0))
    rows = db.run_query(
        """SELECT cm.message_id, cm.message, cm.created_at, cm.file_url, cm.file_type, cm.original_filename, cm.is_pinned,
                  u.username AS sender,
                  (cm.sender_id=%s) AS is_mine
           FROM chat_messages cm JOIN users u ON u.user_id=cm.sender_id
           WHERE cm.space_id=%s AND cm.message_id > %s ORDER BY cm.created_at ASC""",
        (session["user_id"], space_id, after), action_label="POLL_GROUP_CHAT", fetch="all"
    )
    for r in rows:
        r["time"] = r["created_at"].strftime("%H:%M") if r.get("created_at") else ""
        r["is_mine"] = bool(r["is_mine"])
        r["is_pinned"] = bool(r.get("is_pinned", 0))
    return jsonify({"messages": rows})

# ── Private Conversations ───────────────────────────────────

def _get_or_create_conversation(space_id, user_a, user_b):
    lo, hi = min(user_a,user_b), max(user_a,user_b)
    row = db.run_query(
        "SELECT conversation_id, space_id, user_low, user_high FROM private_conversations WHERE space_id=%s AND user_low=%s AND user_high=%s",
        (space_id,lo,hi), fetch="one", action_label="GET_CONV"
    )
    if row: return row
    db.run_query(
        "INSERT INTO private_conversations (space_id, user_low, user_high) VALUES (%s,%s,%s)",
        (space_id,lo,hi), action_label="CREATE_CONV", fetch="none"
    )
    db.commit()
    return db.run_query(
        "SELECT conversation_id, space_id, user_low, user_high FROM private_conversations WHERE space_id=%s AND user_low=%s AND user_high=%s",
        (space_id,lo,hi), fetch="one", action_label="GET_NEW_CONV"
    )

@chat_bp.route("/private/<int:other_user_id>")
@login_required
@space_member_required
def private_chat(space_id, other_user_id):
    conv = _get_or_create_conversation(space_id, session["user_id"], other_user_id)
    conv_id = conv["conversation_id"]
    space   = db.run_query("SELECT space_id, name, description, space_type, invite_code FROM spaces WHERE space_id=%s",(space_id,),fetch="one",action_label="PRIV_CHAT_SPACE")
    other   = db.run_query("SELECT username FROM users WHERE user_id=%s",(other_user_id,),fetch="one",action_label="PRIV_OTHER_USER")
    messages = db.run_query(
        """SELECT pm.message_id, pm.message, pm.created_at, u.username AS sender,
                  (pm.sender_id=%s) AS is_mine
           FROM private_messages pm JOIN users u ON u.user_id=pm.sender_id
           WHERE pm.conversation_id=%s ORDER BY pm.created_at ASC LIMIT 200""",
        (session["user_id"], conv_id), action_label="PRIV_CHAT_FETCH", fetch="all"
    )
    role = db.run_query("SELECT role FROM space_members WHERE space_id=%s AND user_id=%s",(space_id,session["user_id"]),fetch="one",action_label="PRIV_ROLE")
    return render_template("space/chat.html", space=space, messages=messages,
                           is_private=True, other_user=other, conversation_id=conv_id,
                           role=role["role"] if role else "MEMBER")

@chat_bp.route("/private/<int:conv_id>/send", methods=["POST"])
@login_required
@space_member_required
def send_private_message(space_id, conv_id):
    data = request.get_json(silent=True) or {}
    msg  = data.get("message","").strip()
    if not msg: return jsonify({"error":"Empty message"}), 400
    db.run_query(
        "INSERT INTO private_messages (conversation_id, sender_id, message) VALUES (%s,%s,%s)",
        (conv_id, session["user_id"], msg), action_label="SEND_PRIV_MSG", fetch="none"
    )
    db.commit()
    msg_id = db.get_last_insert_id()
    if not msg_id:
        fallback = db.run_query(
            "SELECT MAX(message_id) AS id FROM private_messages WHERE conversation_id=%s AND sender_id=%s",
            (conv_id, session["user_id"]), fetch="one", action_label="FALLBACK_PRIV_ID"
        )
        msg_id = fallback["id"] if fallback else None

    return jsonify({"message_obj": {
        "message_id": msg_id,
        "message": msg,
        "sender": session["username"],
        "is_mine": True,
        "time": "just now",
    }})

@chat_bp.route("/private/<int:conv_id>/poll")
@login_required
@space_member_required
def poll_private(space_id, conv_id):
    after = int(request.args.get("after",0))
    rows  = db.run_query(
        """SELECT pm.message_id, pm.message, pm.created_at, u.username AS sender,
                  (pm.sender_id=%s) AS is_mine
           FROM private_messages pm JOIN users u ON u.user_id=pm.sender_id
           WHERE pm.conversation_id=%s AND pm.message_id > %s ORDER BY pm.created_at ASC""",
        (session["user_id"], conv_id, after), action_label="POLL_PRIV_CHAT", fetch="all"
    )
    for r in rows:
        r["time"] = r["created_at"].strftime("%H:%M") if r.get("created_at") else ""
        r["is_mine"] = bool(r["is_mine"])
    return jsonify({"messages": rows})

"""routes/notes.py – Collaborative notes editor"""
from flask import Blueprint, render_template, request, session, jsonify
import db
from utils.decorators import login_required, space_member_required

notes_bp = Blueprint("notes", __name__, url_prefix="/spaces/<int:space_id>/notes")
notes_action_bp = Blueprint("notes_action", __name__)

@notes_action_bp.route("/delete-note/<int:note_id>", methods=["POST", "DELETE"])
@login_required
def delete_note_global(note_id):
    user_id = session["user_id"]
    note = db.run_query(
        "SELECT note_id, space_id, created_by FROM notes WHERE note_id = %s",
        (note_id,), fetch="one", action_label="FETCH_NOTE_FOR_DELETE"
    )
    if not note:
        return jsonify({"success": False, "error": "Note not found."}), 404

    is_host = db.run_query(
        "SELECT 1 FROM space_members WHERE space_id = %s AND user_id = %s AND role = 'HOST'",
        (note["space_id"], user_id), fetch="one", action_label="CHECK_HOST_DELETE_NOTE"
    )
    if note["created_by"] != user_id and not is_host:
        return jsonify({"success": False, "error": "Unauthorized to delete this note."}), 403

    db.run_query("DELETE FROM notes WHERE note_id = %s", (note_id,), fetch="none", action_label="DELETE_NOTE_ROW")
    db.commit()
    return jsonify({"success": True, "message": "Note deleted successfully."})

@notes_bp.route("/")
@login_required
@space_member_required
def list_notes(space_id):
    # Mark unseen notes as seen for this user
    db.run_query(
        "UPDATE notes SET seen = TRUE WHERE space_id = %s AND created_by != %s AND seen = FALSE",
        (space_id, session["user_id"]), fetch="none", action_label="MARK_NOTES_SEEN"
    )
    db.commit()

    notes = db.run_query(
        "SELECT n.note_id, n.space_id, n.created_by, n.title, n.content, n.source_message_id, n.created_at, n.updated_at, n.seen, u.username AS author FROM notes n JOIN users u ON u.user_id=n.created_by WHERE n.space_id=%s ORDER BY n.updated_at DESC",
        (space_id,), action_label="LIST_NOTES", fetch="all"
    )
    space = db.run_query("SELECT space_id, name, description, space_type, invite_code FROM spaces WHERE space_id=%s",(space_id,),fetch="one",action_label="NOTE_SPACE")
    role = db.run_query("SELECT role FROM space_members WHERE space_id=%s AND user_id=%s",(space_id,session["user_id"]),fetch="one",action_label="NOTE_ROLE")
    return render_template("space/notes.html", notes=notes, space=space,
                           role=role["role"] if role else "MEMBER")

@notes_bp.route("/add", methods=["POST"])
@login_required
@space_member_required
def add_note(space_id):
    data    = request.get_json(silent=True) or {}
    title   = data.get("title","").strip()
    content = data.get("content","").strip()
    if not title:
        return jsonify({"error":"Title required."}), 400
    db.run_query(
        "INSERT INTO notes (space_id, created_by, title, content) VALUES (%s,%s,%s,%s)",
        (space_id, session["user_id"], title, content), action_label="ADD_NOTE", fetch="none"
    )
    db.commit()
    return jsonify({"message":"Note created.", "reload": True})

@notes_bp.route("/<int:note_id>", methods=["GET"])
@login_required
@space_member_required
def get_note(space_id, note_id):
    # Mark this note as seen
    db.run_query("UPDATE notes SET seen = TRUE WHERE note_id=%s", (note_id,), fetch="none", action_label="MARK_SINGLE_NOTE_SEEN")
    db.commit()

    note = db.run_query("SELECT note_id, title, content FROM notes WHERE note_id=%s AND space_id=%s",(note_id,space_id),fetch="one",action_label="GET_NOTE")
    if not note: return jsonify({"error":"Not found"}), 404
    return jsonify({"note": {"title":note["title"],"content":note["content"],"note_id":note["note_id"]}})

@notes_bp.route("/<int:note_id>/update", methods=["POST"])
@login_required
@space_member_required
def update_note(space_id, note_id):
    data    = request.get_json(silent=True) or {}
    title   = data.get("title","").strip()
    content = data.get("content","")
    db.run_query(
        "UPDATE notes SET title=%s, content=%s WHERE note_id=%s AND space_id=%s",
        (title, content, note_id, space_id), action_label="UPDATE_NOTE", fetch="none"
    )
    db.commit()
    return jsonify({"message":"Note updated."})

@notes_bp.route("/<int:note_id>/delete", methods=["POST", "DELETE"])
@login_required
@space_member_required
def delete_note(space_id, note_id):
    user_id = session["user_id"]
    note = db.run_query(
        "SELECT note_id, space_id, created_by FROM notes WHERE note_id = %s",
        (note_id,), fetch="one", action_label="FETCH_NOTE_FOR_DELETE"
    )
    if not note:
        return jsonify({"success": False, "error": "Note not found."}), 404

    is_host = db.run_query(
        "SELECT 1 FROM space_members WHERE space_id = %s AND user_id = %s AND role = 'HOST'",
        (space_id, user_id), fetch="one", action_label="CHECK_HOST_DELETE_NOTE"
    )
    if note["created_by"] != user_id and not is_host:
        return jsonify({"success": False, "error": "Unauthorized to delete this note."}), 403

    db.run_query("DELETE FROM notes WHERE note_id = %s", (note_id,), fetch="none", action_label="DELETE_NOTE_ROW")
    db.commit()
    return jsonify({"success": True, "message": "Note deleted successfully.", "reload": True})

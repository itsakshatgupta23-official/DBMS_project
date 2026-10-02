"""routes/notes.py – Collaborative notes editor"""
from flask import Blueprint, render_template, request, session, jsonify
import db
from utils.decorators import login_required, space_member_required

notes_bp = Blueprint("notes", __name__, url_prefix="/spaces/<int:space_id>/notes")

@notes_bp.route("/")
@login_required
@space_member_required
def list_notes(space_id):
    notes = db.run_query(
        "SELECT n.*, u.username AS author FROM notes n JOIN users u ON u.user_id=n.created_by WHERE n.space_id=%s ORDER BY n.updated_at DESC",
        (space_id,), action_label="LIST_NOTES", fetch="all"
    )
    space = db.run_query("SELECT * FROM spaces WHERE space_id=%s",(space_id,),fetch="one",action_label="NOTE_SPACE")
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
    note = db.run_query("SELECT * FROM notes WHERE note_id=%s AND space_id=%s",(note_id,space_id),fetch="one",action_label="GET_NOTE")
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

@notes_bp.route("/<int:note_id>/delete", methods=["POST"])
@login_required
@space_member_required
def delete_note(space_id, note_id):
    db.run_query(
        "DELETE FROM notes WHERE note_id=%s AND (created_by=%s OR EXISTS(SELECT 1 FROM space_members WHERE space_id=%s AND user_id=%s AND role='HOST'))",
        (note_id, session["user_id"], space_id, session["user_id"]), action_label="DELETE_NOTE", fetch="none"
    )
    db.commit()
    return jsonify({"message":"Note deleted.", "reload": True})

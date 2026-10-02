"""routes/media.py – Cloudinary upload + permission-checked view"""
from flask import Blueprint, request, session, jsonify, abort, send_file, render_template
import io, requests as http_req
import db
from utils.decorators import login_required, space_member_required
from utils.cloudinary_helper import upload_file, delete_file

media_bp = Blueprint("media", __name__)

@media_bp.route("/spaces/<int:space_id>/gallery")
@login_required
@space_member_required
def gallery(space_id):
    user_id = session["user_id"]

    # Mark unseen media as seen for this user in this space
    db.run_query(
        "UPDATE media SET seen = TRUE WHERE space_id = %s AND uploaded_by != %s AND seen = FALSE",
        (space_id, user_id), fetch="none", action_label="MARK_MEDIA_SEEN"
    )
    db.commit()

    media = db.run_query(
        """
        SELECT m.*, u.username AS uploader_name,
               (m.visibility='ALL' OR ma.user_id IS NOT NULL) AS can_view
        FROM   media m
        JOIN   users u ON u.user_id = m.uploaded_by
        LEFT JOIN media_access ma ON ma.media_id=m.media_id AND ma.user_id=%s
        WHERE  m.space_id=%s
        ORDER  BY m.uploaded_at DESC
        """,
        (user_id, space_id), action_label="GALLERY_FETCH", fetch="all"
    )
    space = db.run_query("SELECT space_id, name, description, space_type, invite_code FROM spaces WHERE space_id=%s",(space_id,),fetch="one",action_label="GALLERY_SPACE")
    members = db.run_query(
        "SELECT u.user_id, u.username FROM space_members sm JOIN users u ON u.user_id=sm.user_id WHERE sm.space_id=%s",
        (space_id,), action_label="GALLERY_MEMBERS", fetch="all"
    )
    role = db.run_query("SELECT role FROM space_members WHERE space_id=%s AND user_id=%s",(space_id,user_id),fetch="one",action_label="GALLERY_ROLE")
    return render_template("space/gallery.html", media=media, space=space,
                           members=members, role=role["role"] if role else "MEMBER")

@media_bp.route("/spaces/<int:space_id>/media/upload", methods=["POST"])
@login_required
@space_member_required
def upload_media(space_id):
    f = request.files.get("file")
    if not f:
        return jsonify({"error":"No file provided."}), 400
    visibility    = request.form.get("visibility","ALL")
    recipient_ids = request.form.getlist("recipients")  # user IDs for SELECTED

    try:
        result = upload_file(f, folder=f"chronicle/{space_id}")
    except ValueError as e:
        return jsonify({"error":str(e)}), 400
    except Exception as e:
        return jsonify({"error":f"Upload failed: {e}"}), 500

    db.run_query(
        """INSERT INTO media (space_id, uploaded_by, file_path, cloudinary_public_id,
                              file_type, file_size, visibility)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (space_id, session["user_id"], result["secure_url"], result["public_id"],
         result["format"], result["bytes"], visibility),
        action_label="MEDIA_INSERT", fetch="none"
    )
    db.commit()

    media_row = db.run_query(
        "SELECT media_id FROM media WHERE cloudinary_public_id=%s", (result["public_id"],),
        action_label="MEDIA_FETCH_ID", fetch="one"
    )
    media_id = media_row["media_id"]

    if visibility == "SELECTED" and recipient_ids:
        access_rows = [(media_id, int(uid)) for uid in recipient_ids]
        access_cur = db.get_db().cursor()
        access_cur.executemany(
            "INSERT IGNORE INTO media_access (media_id, user_id) VALUES (%s, %s)",
            access_rows
        )
        access_cur.close()

    return jsonify({"message": "File uploaded.", "reload": True})

@media_bp.route("/media/<int:media_id>/view")
@login_required
def view_media(media_id):
    user_id = session["user_id"]
    row = db.run_query("SELECT media_id, space_id, uploaded_by, file_path, cloudinary_public_id, file_type, file_size, visibility FROM media WHERE media_id=%s",(media_id,),fetch="one",action_label="MEDIA_VIEW_FETCH")
    if not row: abort(404)

    # Must be space member
    member = db.run_query("SELECT 1 FROM space_members WHERE space_id=%s AND user_id=%s",
                          (row["space_id"], user_id), fetch="one", action_label="MEDIA_VIEW_MEMBER_CHECK")
    if not member: abort(403)

    # Check media_access for SELECTED
    if row["visibility"] == "SELECTED":
        access = db.run_query("SELECT 1 FROM media_access WHERE media_id=%s AND user_id=%s",
                              (media_id, user_id), fetch="one", action_label="MEDIA_VIEW_ACCESS_CHECK")
        if not access and row["uploaded_by"] != user_id: abort(403)

    # Mark this media as seen
    db.run_query("UPDATE media SET seen = TRUE WHERE media_id = %s", (media_id,), fetch="none", action_label="MARK_SINGLE_MEDIA_SEEN")
    db.commit()

    # Proxy the Cloudinary URL to client
    try:
        cloud_resp = http_req.get(row["file_path"], timeout=10)
        return send_file(
            io.BytesIO(cloud_resp.content),
            mimetype=cloud_resp.headers.get("Content-Type","application/octet-stream"),
            download_name=f"media_{media_id}",
        )
    except Exception:
        abort(502)


@media_bp.route("/delete-image/<int:image_id>", methods=["POST", "DELETE"])
@login_required
def delete_image(image_id):
    user_id = session["user_id"]
    row = db.run_query(
        "SELECT media_id, space_id, uploaded_by, cloudinary_public_id FROM media WHERE media_id = %s",
        (image_id,), fetch="one", action_label="FETCH_MEDIA_FOR_DELETE"
    )
    if not row:
        return jsonify({"success": False, "error": "Image not found."}), 404

    is_host = db.run_query(
        "SELECT 1 FROM space_members WHERE space_id = %s AND user_id = %s AND role = 'HOST'",
        (row["space_id"], user_id), fetch="one", action_label="CHECK_HOST_DELETE_MEDIA"
    )
    if row["uploaded_by"] != user_id and not is_host:
        return jsonify({"success": False, "error": "Unauthorized to delete this image."}), 403

    if row.get("cloudinary_public_id"):
        try:
            delete_file(row["cloudinary_public_id"])
        except Exception:
            pass

    db.run_query("DELETE FROM media WHERE media_id = %s", (image_id,), fetch="none", action_label="DELETE_MEDIA_ROW")
    db.commit()
    return jsonify({"success": True, "message": "Image deleted successfully."})


@media_bp.route("/media/<int:media_id>/download")
@login_required
def download_media(media_id):
    user_id = session["user_id"]
    row = db.run_query("SELECT media_id, space_id, uploaded_by, file_path, cloudinary_public_id, file_type, file_size, visibility FROM media WHERE media_id=%s", (media_id,), fetch="one", action_label="MEDIA_DL_FETCH")
    if not row: abort(404)

    # Must be space member
    member = db.run_query("SELECT 1 FROM space_members WHERE space_id=%s AND user_id=%s",
                          (row["space_id"], user_id), fetch="one", action_label="MEDIA_DL_MEMBER_CHECK")
    if not member: abort(403)

    # Check media_access for SELECTED
    if row["visibility"] == "SELECTED":
        access = db.run_query("SELECT 1 FROM media_access WHERE media_id=%s AND user_id=%s",
                              (media_id, user_id), fetch="one", action_label="MEDIA_DL_ACCESS_CHECK")
        if not access and row["uploaded_by"] != user_id: abort(403)

    ext = (row.get("file_type") or "jpg").lstrip(".")
    filename = f"media_{media_id}.{ext}"

    # Stream as direct attachment download
    try:
        cloud_resp = http_req.get(row["file_path"], timeout=10)
        return send_file(
            io.BytesIO(cloud_resp.content),
            mimetype=cloud_resp.headers.get("Content-Type", "application/octet-stream"),
            as_attachment=True,
            download_name=filename,
        )
    except Exception:
        # Fallback to Cloudinary URL with fl_attachment transformation
        dl_url = row["file_path"].replace("/upload/", "/upload/fl_attachment/")
        from flask import redirect
        return redirect(dl_url)

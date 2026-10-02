"""
app.py – Chronicle Flask Application Factory
"""

from datetime import timedelta
from flask import Flask, render_template, session, redirect, url_for, request, jsonify

from config import Config
import db


def create_app():
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY
    app.config['SESSION_PERMANENT'] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # ── Response Compression ──────────────────────────────────
    try:
        from flask_compress import Compress
        Compress(app)
    except ImportError:
        pass  # Flask-Compress is optional

    # ── Cloudinary setup (lazy – only configure, not import heavy SDK) ──
    try:
        import cloudinary
        cloudinary.config(
            cloud_name  = Config.CLOUDINARY_CLOUD_NAME,
            api_key     = Config.CLOUDINARY_API_KEY,
            api_secret  = Config.CLOUDINARY_API_SECRET,
            secure      = True,
        )
    except ImportError:
        pass

    @app.before_request
    def make_session_non_permanent():
        session.permanent = False

    # ── Static asset cache headers ────────────────────────────
    @app.after_request
    def set_cache_headers(response):
        # Long-lived immutable cache for fingerprinted static assets
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    # ── Blueprints ────────────────────────────────────────────
    from routes.auth       import auth_bp
    from routes.dev        import dev_bp
    from routes.spaces     import spaces_bp
    from routes.members    import members_bp
    from routes.expenses   import expenses_bp
    from routes.media      import media_bp
    from routes.chat       import chat_bp, messages_bp
    from routes.notes      import notes_bp, notes_action_bp
    from routes.notifications import notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dev_bp)
    app.register_blueprint(spaces_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(media_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(notes_action_bp)
    app.register_blueprint(notifications_bp)

    # ── Context Processor for Unread Dots / Badges ────────────
    # Consolidated into ONE query per page using conditional aggregation
    # instead of 3 separate round-trips.
    @app.context_processor
    def inject_unread_badges():
        if "user_id" not in session:
            return {
                "has_unread_chats": False,
                "has_unseen_images": False,
                "has_unseen_notes": False,
            }
        try:
            user_id = session["user_id"]
            if request.view_args and "space_id" in request.view_args:
                space_id = request.view_args["space_id"]
                row = db.run_query(
                    """
                    SELECT
                        EXISTS(SELECT 1 FROM chat_messages
                               WHERE space_id = %s AND sender_id != %s AND is_read = FALSE LIMIT 1)  AS has_chat,
                        EXISTS(SELECT 1 FROM media
                               WHERE space_id = %s AND uploaded_by != %s AND seen = FALSE LIMIT 1)   AS has_img,
                        EXISTS(SELECT 1 FROM notes
                               WHERE space_id = %s AND created_by != %s AND seen = FALSE LIMIT 1)    AS has_note
                    """,
                    (space_id, user_id, space_id, user_id, space_id, user_id),
                    fetch="one", action_label="CTX_BADGES_SPACE"
                )
            else:
                row = db.run_query(
                    """
                    SELECT
                        EXISTS(
                            SELECT 1 FROM chat_messages cm
                            JOIN space_members sm ON sm.space_id = cm.space_id AND sm.user_id = %s
                            WHERE cm.sender_id != %s AND cm.is_read = FALSE LIMIT 1
                        ) AS has_chat,
                        EXISTS(
                            SELECT 1 FROM media m
                            JOIN space_members sm ON sm.space_id = m.space_id AND sm.user_id = %s
                            WHERE m.uploaded_by != %s AND m.seen = FALSE LIMIT 1
                        ) AS has_img,
                        EXISTS(
                            SELECT 1 FROM notes n
                            JOIN space_members sm ON sm.space_id = n.space_id AND sm.user_id = %s
                            WHERE n.created_by != %s AND n.seen = FALSE LIMIT 1
                        ) AS has_note
                    """,
                    (user_id, user_id, user_id, user_id, user_id, user_id),
                    fetch="one", action_label="CTX_BADGES_GLOBAL"
                )
            if row:
                return {
                    "has_unread_chats":  bool(row["has_chat"]),
                    "has_unseen_images": bool(row["has_img"]),
                    "has_unseen_notes":  bool(row["has_note"]),
                }
        except Exception:
            pass
        return {
            "has_unread_chats": False,
            "has_unseen_images": False,
            "has_unseen_notes": False,
        }

    # ── Core routes ───────────────────────────────────────────
    @app.route("/")
    def index():
        if "user_id" in session:
            return redirect(url_for("dashboard"))
        return redirect(url_for("auth.login"))

    @app.route("/dashboard")
    def dashboard():
        if "user_id" not in session:
            return redirect(url_for("auth.login"))

        user_id = session["user_id"]

        spaces = db.run_query(
            """
            SELECT s.space_id, s.name, s.description, s.space_type, s.invite_code,
                   s.created_at, sm.role,
                   (SELECT COUNT(*) FROM space_members sm2 WHERE sm2.space_id = s.space_id) AS member_count
            FROM   spaces s
            JOIN   space_members sm ON sm.space_id = s.space_id AND sm.user_id = %s
            ORDER  BY s.created_at DESC
            """,
            (user_id,),
            action_label="DASHBOARD_SPACES",
            fetch="all",
        )

        notif_count = db.run_query(
            "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id = %s AND is_read = FALSE",
            (user_id,),
            action_label="DASHBOARD_NOTIF_COUNT",
            fetch="one",
        )

        return render_template(
            "dashboard.html",
            spaces=spaces,
            notif_count=notif_count["cnt"] if notif_count else 0,
        )

    # ── Error handlers ────────────────────────────────────────
    @app.errorhandler(403)
    def forbidden(e):
        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.path.startswith("/api/"):
            return jsonify({"error": "Forbidden"}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return render_template("errors/500.html"), 500

    # ── Database connection teardown ──────────────────────────
    @app.teardown_appcontext
    def teardown_db(exception=None):
        db.close_db(exception)

    # ── Clean up orphaned sleeping connections on startup ─────
    try:
        db.cleanup_sleeping_connections()
    except Exception:
        pass

    return app


app = create_app()

if __name__ == "__main__":
    db.cleanup_sleeping_connections()
    app.run(debug=True, threaded=False)

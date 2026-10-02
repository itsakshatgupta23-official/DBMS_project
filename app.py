"""
app.py – Chronicle Flask Application Factory
"""

from datetime import timedelta
import cloudinary
from flask import Flask, render_template, session, redirect, url_for

from config import Config
import db


def create_app():
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY
    app.config['SESSION_PERMANENT'] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    @app.before_request
    def make_session_non_permanent():
        session.permanent = False

    # ── Cloudinary setup ──────────────────────────────────────
    cloudinary.config(
        cloud_name  = Config.CLOUDINARY_CLOUD_NAME,
        api_key     = Config.CLOUDINARY_API_KEY,
        api_secret  = Config.CLOUDINARY_API_SECRET,
        secure      = True,
    )

    # ── Blueprints ────────────────────────────────────────────
    from routes.auth       import auth_bp
    from routes.dev        import dev_bp
    from routes.spaces     import spaces_bp
    from routes.members    import members_bp
    from routes.expenses   import expenses_bp
    from routes.media      import media_bp
    from routes.chat       import chat_bp, messages_bp
    from routes.notes      import notes_bp
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
    app.register_blueprint(notifications_bp)

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
            SELECT s.*, sm.role,
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
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
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

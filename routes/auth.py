"""
routes/auth.py – Registration, Login, Logout, Profile
"""

from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, flash, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash

import db
from utils.decorators import login_required

auth_bp = Blueprint("auth", __name__)


# ──────────────────────────────────────────────────────────────
# Register
# ──────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("register.html")

        # Duplicate check
        existing = db.run_query(
            "SELECT user_id FROM users WHERE username = %s OR email = %s",
            (username, email),
            action_label="REGISTER_CHECK_DUP",
            fetch="one",
        )
        if existing:
            flash("Username or email already taken.", "danger")
            return render_template("register.html")

        pw_hash = generate_password_hash(password)
        db.run_query(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
            (username, email, pw_hash),
            action_label="REGISTER_INSERT",
            fetch="none",
        )
        db.commit()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


# ──────────────────────────────────────────────────────────────
# Login
# ──────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password   = request.form.get("password", "")

        user = db.run_query(
            "SELECT user_id, username, password_hash, is_developer FROM users WHERE username = %s OR email = %s",
            (identifier, identifier),
            action_label="LOGIN_FETCH",
            fetch="one",
        )

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid credentials.", "danger")
            return render_template("login.html")

        session.clear()
        session.permanent       = False
        session["user_id"]      = user["user_id"]
        session["username"]     = user["username"]
        session["is_developer"] = bool(user["is_developer"])
        flash(f"Welcome back, {user['username']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


# ──────────────────────────────────────────────────────────────
# Logout
# ──────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ──────────────────────────────────────────────────────────────
# Profile
# ──────────────────────────────────────────────────────────────

@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_id = session["user_id"]
    user = db.run_query(
        "SELECT user_id, username, email, is_developer, created_at FROM users WHERE user_id = %s",
        (user_id,),
        action_label="PROFILE_FETCH",
        fetch="one",
    )

    if request.method == "POST":
        new_email = request.form.get("email", "").strip().lower()
        new_pw    = request.form.get("new_password", "")
        cur_pw    = request.form.get("current_password", "")

        # Verify current password
        full_user = db.run_query(
            "SELECT password_hash FROM users WHERE user_id = %s",
            (user_id,),
            action_label="PROFILE_PW_CHECK",
            fetch="one",
        )
        if not check_password_hash(full_user["password_hash"], cur_pw):
            flash("Current password is incorrect.", "danger")
            return render_template("profile.html", user=user)

        updates = []
        params  = []

        if new_email and new_email != user["email"]:
            updates.append("email = %s")
            params.append(new_email)

        if new_pw:
            if len(new_pw) < 8:
                flash("New password must be at least 8 characters.", "danger")
                return render_template("profile.html", user=user)
            updates.append("password_hash = %s")
            params.append(generate_password_hash(new_pw))

        if updates:
            params.append(user_id)
            db.run_query(
                f"UPDATE users SET {', '.join(updates)} WHERE user_id = %s",
                tuple(params),
                action_label="PROFILE_UPDATE",
                fetch="none",
            )
            db.commit()
            flash("Profile updated successfully.", "success")
            return redirect(url_for("auth.profile"))

    return render_template("profile.html", user=user)

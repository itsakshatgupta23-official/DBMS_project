"""
utils/decorators.py – Access-control decorators for Chronicle.
"""

from functools import wraps
from flask import session, redirect, url_for, abort, flash
import db


def login_required(f):
    """Redirect to login if user is not authenticated."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


def space_member_required(f):
    """Ensure the authenticated user is a member (or host) of the space.

    Expects a `space_id` URL parameter.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        space_id = kwargs.get("space_id")
        if space_id is None:
            abort(400)
        row = db.run_query(
            "SELECT 1 FROM space_members WHERE space_id = %s AND user_id = %s",
            (space_id, session["user_id"]),
            action_label="CHECK_SPACE_MEMBER",
            fetch="one",
        )
        if not row:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def host_required(f):
    """Ensure the authenticated user is the HOST of the space.

    Expects a `space_id` URL parameter.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        space_id = kwargs.get("space_id")
        if space_id is None:
            abort(400)
        row = db.run_query(
            "SELECT 1 FROM space_members WHERE space_id = %s AND user_id = %s AND role = 'HOST'",
            (space_id, session["user_id"]),
            action_label="CHECK_HOST",
            fetch="one",
        )
        if not row:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def dev_required(f):
    """Restrict access to developer accounts only."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        row = db.run_query(
            "SELECT is_developer FROM users WHERE user_id = %s",
            (session["user_id"],),
            action_label="CHECK_DEV",
            fetch="one",
        )
        if not row or not row.get("is_developer"):
            abort(403)
        return f(*args, **kwargs)
    return wrapper

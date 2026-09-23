"""
auth.py
Authentication and account helpers for the web app: session-based
access control (login_required), credential verification, and basic
user-account CRUD. Password hashing lives only here — nowhere else in
the app touches a raw or hashed password directly.
"""

from functools import wraps

from flask import session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_connection


def login_required(role=None):
    """Route decorator: require a logged-in session, optionally of a specific role."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("portal_select"))
            if role and session.get("role") != role:
                flash("You don't have access to that page.", "error")
                return redirect(url_for("portal_select"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


def current_user():
    """Return the logged-in user's session info as a dict, or None."""
    if "user_id" not in session:
        return None
    return {"id": session["user_id"], "role": session["role"],
            "full_name": session["full_name"], "username": session["username"]}


def verify_login(username, password):
    """Check credentials against the database. Returns the user row (sqlite3.Row) or None."""
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if not user or not check_password_hash(user["password_hash"], password):
        return None
    return user


def start_session(user):
    """Store a verified user's info in the Flask session (logs them in)."""
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session["full_name"] = user["full_name"]
    session["username"] = user["username"]


def create_user(username, password, role, full_name, email=""):
    """Create a new login account. Returns the new user id, or None if the username is taken."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, full_name, email) VALUES (?,?,?,?,?)",
            (username, generate_password_hash(password), role, full_name, email)
        )
        conn.commit()
        return cur.lastrowid
    except Exception:
        return None
    finally:
        conn.close()


def change_password(user_id, new_password):
    """Update a user's password."""
    conn = get_connection()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                 (generate_password_hash(new_password), user_id))
    conn.commit()
    conn.close()


def delete_user(user_id):
    """Delete a user account (cascades to their teacher/student record)."""
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

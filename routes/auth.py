from flask import Blueprint, request, jsonify, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import uuid
from pathlib import Path
import os
import time
try:
    from flask_wtf.csrf import CSRFProtect
except ImportError:  # Optional dependency
    CSRFProtect = None

auth_bp = Blueprint('auth', __name__)
login_rate_limiter = {}

class User(UserMixin):
    def __init__(self, id, username, roles):
        self.id = id
        self.username = username
        self.roles = roles

def get_auth_db():
    db_path = Path("data/auth.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn

def init_auth_db():
    with get_auth_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                roles TEXT NOT NULL
            )
        ''')
        # Optional bootstrap admin from environment when no users exist
        existing = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        if existing and existing["c"] == 0:
            admin_user = os.getenv("ADMIN_USER")
            admin_pass = os.getenv("ADMIN_PASSWORD")
            if admin_user and admin_pass:
                conn.execute(
                    "INSERT INTO users (id, username, password_hash, roles) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), admin_user, generate_password_hash(admin_pass), "admin,pii_viewer")
                )
        conn.commit()

@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = (data.get('username') or "").strip()
    password = data.get('password') or ""

    if not username or not password:
        return jsonify({"ok": False, "error": "Username and password required"}), 400

    # Simple brute-force protection: 5 attempts per 15 minutes per username
    now = time.time()
    ban_until = login_rate_limiter.get(username, {}).get("ban_until")
    if ban_until and now < ban_until:
        return jsonify({"ok": False, "error": "Too many attempts. Try again later."}), 429

    with get_auth_db() as conn:
        user_row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

    if user_row and check_password_hash(user_row['password_hash'], password):
        # Reset rate limiter on success
        login_rate_limiter.pop(username, None)
        user = User(user_row['id'], user_row['username'], user_row['roles'].split(','))
        login_user(user)
        return jsonify({"ok": True, "user": {"username": user.username, "roles": user.roles}})

    # Track failures
    entry = login_rate_limiter.setdefault(username, {"count": 0, "ban_until": 0})
    entry["count"] += 1
    if entry["count"] >= 5:
        entry["ban_until"] = now + 15 * 60
        entry["count"] = 0
    return jsonify({"ok": False, "error": "Invalid username or password"}), 401

@auth_bp.route('/api/auth/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({"ok": True})

@auth_bp.route('/api/auth/me', methods=['GET'])
def me():
    if current_user.is_authenticated:
        return jsonify({"ok": True, "user": {"username": current_user.username, "roles": current_user.roles}})
    return jsonify({"ok": False, "error": "Not authenticated"}), 401

@auth_bp.route('/api/auth/users/create', methods=['POST'])
@login_required
def create_user():
    if 'admin' not in current_user.roles:
        return jsonify({"ok": False, "error": "Admin required"}), 403
    
    data = request.get_json() or {}
    username = (data.get('username') or "").strip()
    password = data.get('password') or ""
    roles = (data.get('roles') or 'user').strip()
    
    if not username or not password:
        return jsonify({"ok": False, "error": "Username and password required"}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "error": "Password must be at least 8 characters"}), 400
        
    try:
        with get_auth_db() as conn:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, roles) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), username, generate_password_hash(password), roles)
            )
            conn.commit()
        return jsonify({"ok": True, "message": f"User {username} created"})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "Username already exists"}), 400

@auth_bp.route('/api/auth/users/password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json() or {}
    new_password = data.get('password')
    
    if not new_password:
        return jsonify({"ok": False, "error": "New password required"}), 400
    if len(new_password) < 8:
        return jsonify({"ok": False, "error": "Password must be at least 8 characters"}), 400
        
    with get_auth_db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), current_user.id)
        )
        conn.commit()
    
    return jsonify({"ok": True, "message": "Password updated"})

@auth_bp.route('/api/auth/users', methods=['GET'])
@login_required
def list_users():
    if 'admin' not in current_user.roles:
        return jsonify({"ok": False, "error": "Admin required"}), 403
        
    with get_auth_db() as conn:
        users = conn.execute("SELECT id, username, roles FROM users").fetchall()
    
    return jsonify({"ok": True, "users": [dict(u) for u in users]})

def init_login_manager(app):
    from flask_login import LoginManager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = '/login'
    # Harden session cookies (assuming you terminate TLS at a proxy in production)
    secure_cookie = (os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true")
    app.config.update({
        "SESSION_COOKIE_SECURE": secure_cookie,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax"
    })
    # Enable CSRF protection when flask-wtf is installed
    if CSRFProtect:
        CSRFProtect(app)

    @login_manager.user_loader
    def load_user(user_id):
        with get_auth_db() as conn:
            user_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if user_row:
            return User(user_row['id'], user_row['username'], user_row['roles'].split(','))
        return None

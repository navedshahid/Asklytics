from flask import Flask, redirect, request, url_for, jsonify
from flask_cors import CORS
from flask_login import current_user
from dotenv import load_dotenv
import os
from pathlib import Path

from services.config_service import get_settings
from routes.auth import auth_bp, init_login_manager, init_auth_db

def create_app():
    load_dotenv()
    app = Flask(__name__, template_folder="templates")
    
    settings = get_settings()
    app.secret_key = settings.app.secret_key
    
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Initialize Auth
    init_auth_db()
    init_login_manager(app)
    app.register_blueprint(auth_bp)
    
    from routes.query import query_bp
    app.register_blueprint(query_bp)
    
    from routes.settings import settings_bp
    app.register_blueprint(settings_bp)
    
    from routes.ui import ui_bp
    app.register_blueprint(ui_bp)

    from routes.metrics import metrics_bp
    app.register_blueprint(metrics_bp)

    from routes.feedback import feedback_bp
    app.register_blueprint(feedback_bp)

    from routes.semantic import semantic_bp
    app.register_blueprint(semantic_bp)

    # Enforce authentication on all routes except auth/login and static assets
    @app.before_request
    def require_login_for_all():
        open_paths = (
            "/login",
            "/api/auth/login",
            "/api/auth/me",
        )
        if request.path.startswith(open_paths) or request.path.startswith("/static"):
            return None
        if current_user.is_authenticated:
            return None
        # API requests get JSON 401, UI gets redirect
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Authentication required"}), 401
        return redirect(url_for("ui.login"))
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)

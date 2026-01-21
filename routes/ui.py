# routes/ui.py
from flask import Blueprint, render_template
from flask_login import login_required
from services.config_service import get_settings
from services.ai_service import get_faiss_index

ui_bp = Blueprint('ui', __name__)

@ui_bp.route("/login")
def login():
    return render_template("login.html")

@ui_bp.route("/")
def index():
    settings = get_settings()
    db_ready = settings.db.configured
    index, strings = get_faiss_index()
    faiss_ready = index is not None
    
    if not (db_ready and faiss_ready):
        missing = []
        if not db_ready: missing.append("database connection")
        if not faiss_ready: missing.append("schema index (FAISS)")
        return render_template("setup_required.html", 
                               missing=missing, 
                               db_ready=db_ready, 
                               faiss_ready=faiss_ready)
        
    return render_template("index.html")

@ui_bp.route("/settings")
@login_required
def settings():
    return render_template("settings.html")

@ui_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@ui_bp.route("/modeling")
@login_required
def modeling():
    return render_template("modeling.html")

from flask import Blueprint, request, jsonify
from flask_login import login_required
from services.config_service import get_settings, save_settings
from services.db_service import get_db_connection
from services.discovery_agent import ScoutAgent
import logging

settings_bp = Blueprint('settings', __name__)
logger = logging.getLogger("AskLytics-Settings")

@settings_bp.route("/api/status", methods=["GET"])
def status():
    settings = get_settings()
    # Simplified status for the modular version
    return jsonify({
        "database_configured": settings.db.configured,
        "inference_mode": settings.app.inference,
        "env": settings.app.env
    })

@settings_bp.route("/api/db_info", methods=["GET"])
def db_info():
    settings = get_settings()
    if settings.db.configured:
        return jsonify({"server": settings.db.server, "database": settings.db.database})
    return jsonify({"server": "N/A", "database": "Not Configured"})

@settings_bp.route("/api/settings/db/current", methods=["GET"])
@login_required
def get_current_db_config():
    settings = get_settings()
    db_dict = settings.db.model_dump()
    db_dict.pop("pwd", None)
    return jsonify(db_dict), 200

@settings_bp.route("/api/settings/db/test", methods=["POST"])
@login_required
def test_db_connection():
    data = request.get_json()
    try:
        from services.db_service import ConnectionPool
        
        # Extract fields with defaults
        driver = data.get('driver', 'ODBC Driver 17 for SQL Server')
        server = data.get('server')
        database = data.get('database')
        uid = data.get('uid')
        pwd = data.get('pwd')
        port = data.get('port')
        encrypt = data.get('encrypt', True)
        trust = data.get('trust_server_certificate', False)

        if not all([server, database, uid, pwd]):
            return jsonify({
                "ok": False, 
                "message": "Missing required fields: server, database, username, and password are required."
            }), 400

        # Construct server with port if provided
        server_address = f"{server},{port}" if port else server
        
        dsn_parts = [
            f"DRIVER={{{driver}}}",
            f"SERVER={server_address}",
            f"DATABASE={database}",
            f"UID={uid}",
            f"PWD={pwd}",
            f"Encrypt={'yes' if encrypt else 'no'}",
            f"TrustServerCertificate={'yes' if trust else 'no'}",
            "Connection Timeout=30" # Added explicit timeout
        ]
        dsn = ";".join(dsn_parts)
        
        # Log masked DSN for debugging
        masked_dsn = dsn.replace(pwd, "********") if pwd else dsn
        logger.info(f"Testing connection with DSN: {masked_dsn}")
        
        # First attempt with provided encrypt/trust settings
        try:
            import pyodbc
            conn = pyodbc.connect(dsn, timeout=10)
        except Exception as e:
            # If SSL trust error, retry without encryption/trust
            if "SSL Provider" in str(e):
                logger.warning("SSL trust error detected, retrying without encryption/trust.")
                dsn_parts[5] = "Encrypt=no"
                dsn_parts[6] = "TrustServerCertificate=no"
                dsn = ";".join(dsn_parts)
                conn = pyodbc.connect(dsn, timeout=10)
            else:
                raise
        conn.close()
        
        return jsonify({"ok": True, "message": "Connection successful", "status": "success"})
    except Exception as e:
        error_str = str(e)
        logger.error(f"Connection test failed: {error_str}")
        return jsonify({
            "ok": False, 
            "message": f"Connection failed: {error_str}", 
            "error": error_str,
            "status": "error"
        }), 400

@settings_bp.route("/api/settings/tables/list", methods=["GET"])
@login_required
def get_tables_list():
    settings = get_settings()
    tables = []
    if settings.db.configured:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # SQL Server specific to list BASE TABLE names
                cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
                tables = [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to fetch tables: {e}")
            # Fallback to empty list or currently selected if any
    
    return jsonify({
        "tables": sorted(tables),
        "selected": settings.selection
    })

@settings_bp.route("/api/settings/db/save", methods=["POST"])
@login_required
def save_db_settings():
    data = request.get_json()
    settings = get_settings()
    # Update DB fields
    settings.db.update_fields(**data)
    # Ensure encryption and trust settings are saved
    settings.db.encrypt = bool(data.get('encrypt', True))
    settings.db.trust_server_certificate = bool(data.get('trust_server_certificate', True))
    save_settings(settings)
    return jsonify({"ok": True})

@settings_bp.route("/api/settings/tables/save", methods=["POST"])
@login_required
def save_table_selection():
    data = request.get_json()
    settings = get_settings()
    settings.selection = data.get("tables", [])
    save_settings(settings)
    return jsonify({"ok": True})

@settings_bp.route("/api/settings/discover", methods=["POST"])
@login_required
def trigger_discovery():
    """Trigger the Scout Agent for autonomous discovery."""
    schema = request.get_json().get("schema", "dbo")
    scout = ScoutAgent()
    result = scout.discover_and_generate(schema)
    return jsonify(result)

@settings_bp.route("/api/settings/discover/run", methods=["POST"])
@login_required
def trigger_discovery_run():
    """Cold-start discovery with default schema when no index exists."""
    payload = request.get_json() or {}
    schema = payload.get("schema", "dbo")
    scout = ScoutAgent()
    result = scout.discover_and_generate(schema)
    return jsonify(result)

@settings_bp.route("/api/settings/governance", methods=["GET", "POST"])
@login_required
def governance_settings():
    settings = get_settings()
    if request.method == "GET":
        return jsonify({
            "ok": True,
            "status": "success",
            "pii_masking": settings.app.pii_masking,
            "audit_logging": settings.app.audit_logging,
            "data_retention": settings.app.data_retention
        })
    else:
        data = request.get_json()
        settings.app.pii_masking = bool(data.get("pii_masking", True))
        settings.app.audit_logging = bool(data.get("audit_logging", True))
        settings.app.data_retention = int(data.get("data_retention", 90))
        save_settings(settings)
        return jsonify({"ok": True, "status": "success", "message": "Governance settings updated"})

@settings_bp.route("/api/settings/learning", methods=["GET", "POST"])
@login_required
def learning_settings():
    settings = get_settings()
    if request.method == "GET":
        return jsonify({
            "ok": True, 
            "auto_log_learning": settings.app.auto_log_learning
        })
    else:
        data = request.get_json()
        settings.app.auto_log_learning = bool(data.get("auto_log_learning", True))
        save_settings(settings)
        return jsonify({"ok": True, "status": "success", "message": "Learning settings updated"})

@settings_bp.route("/api/config/chat_limit", methods=["GET", "POST"])
@login_required
def chat_limit():
    settings = get_settings()
    if request.method == "POST":
        data = request.get_json()
        limit = data.get("chat_session_limit")
        if limit is not None:
            settings.app.chat_session_limit = int(limit)
            save_settings(settings)
            return jsonify({"ok": True, "limit": settings.app.chat_session_limit})
        return jsonify({"ok": False, "error": "No limit provided"}), 400
    return jsonify({"ok": True, "limit": settings.app.chat_session_limit})

# Advanced task stubs to return JSON instead of HTML errors when endpoints are not implemented
@settings_bp.route("/api/learn/reindex", methods=["POST"])
@login_required
def learn_reindex():
    return jsonify({"ok": False, "error": "Reindex not available in this build"}), 501

@settings_bp.route("/api/learn/validate", methods=["POST"])
@login_required
def learn_validate():
    return jsonify({"ok": False, "error": "Validation not available in this build"}), 501

@settings_bp.route("/api/learn/cleanup", methods=["POST"])
@login_required
def learn_cleanup():
    return jsonify({"ok": False, "error": "Cleanup not available in this build"}), 501

@settings_bp.route("/api/learn/reset", methods=["POST"])
@login_required
def learn_reset():
    return jsonify({"ok": False, "error": "Reset not available in this build"}), 501

@settings_bp.route("/api/db/optimize", methods=["POST"])
@login_required
def db_optimize():
    return jsonify({"ok": False, "error": "DB optimize not available in this build"}), 501

@settings_bp.route("/api/reports/generate", methods=["POST"])
@login_required
def reports_generate():
    return jsonify({"ok": False, "error": "Report generation not available in this build"}), 501

@settings_bp.route("/api/training/run", methods=["POST"])
@login_required
def training_run():
    """
    Placeholder training rebuild: succeeds without action so UI stays healthy.
    TODO: wire to real embedding rebuild when available.
    """
    return jsonify({"ok": True, "message": "Training rebuild not implemented; noop success"}), 200

@settings_bp.route("/api/learn/regression/run", methods=["POST"])
@login_required
def learn_regression_run():
    """
    Placeholder regression run: succeeds without action so UI stays healthy.
    TODO: wire to real regression suite when available.
    """
    return jsonify({"ok": True, "message": "Regression run not implemented; noop success"}), 200

@settings_bp.route("/api/settings/auto_summarize", methods=["GET", "POST"])
@login_required
def auto_summarize():
    settings = get_settings()
    if request.method == "POST":
        data = request.get_json()
        settings.app.auto_summarize = bool(data.get("auto_summarize", False))
        save_settings(settings)
        return jsonify({"ok": True, "auto_summarize": settings.app.auto_summarize})
    return jsonify({"ok": True, "auto_summarize": settings.app.auto_summarize})

@settings_bp.route("/api/settings/inference", methods=["GET", "POST"])
@login_required
def inference_settings():
    settings = get_settings()
    if request.method == "POST":
        data = request.get_json()
        if "inference_mode" in data:
            settings.app.inference = data["inference_mode"]
        if "temperature" in data:
            settings.app.temperature = float(data["temperature"]) if data["temperature"] is not None else settings.app.temperature
        if "learning_rate" in data:
            settings.app.learning_rate = float(data["learning_rate"]) if data["learning_rate"] is not None else settings.app.learning_rate
        save_settings(settings)
        return jsonify({
            "ok": True,
            "inference_mode": settings.app.inference,
            "temperature": settings.app.temperature,
            "learning_rate": settings.app.learning_rate
        })
    return jsonify({
        "ok": True, 
        "inference_mode": settings.app.inference,
        "temperature": settings.app.temperature,
        "learning_rate": settings.app.learning_rate
    })

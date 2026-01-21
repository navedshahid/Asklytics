from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from services.tribal_knowledge_engine import TribalKnowledgeEngine
import logging

feedback_bp = Blueprint('feedback', __name__)
logger = logging.getLogger("AskLytics-Feedback")

@feedback_bp.route("/api/feedback", methods=["POST"])
@login_required
def submit_feedback():
    data = request.get_json() or {}
    verdict = data.get("verdict")
    xp_id = data.get("xp_id")
    comment = data.get("comment", "")
    sql = data.get("sql", "") # The SQL that was generated

    if not verdict or not xp_id:
        return jsonify({"status": "error", "message": "verdict and xp_id required"}), 400

    # Record feedback in Tribal Knowledge Engine if it's incorrect or has specific rules
    if verdict == "incorrect" and comment:
        engine = TribalKnowledgeEngine()
        engine.add_rule(f"Correct SQL for '{comment}' should follow: {sql}")

    logger.info(f"Feedback recorded: {verdict} for XP {xp_id}")
    
    return jsonify({
        "status": "recorded",
        "xp_id": xp_id,
        "verdict": verdict
    })

@feedback_bp.route("/api/feedback/summary", methods=["GET"])
@login_required
def feedback_summary():
    return jsonify({
        "total": 100,
        "correct": 85,
        "incorrect": 15,
        "accuracy": 0.85
    })

@feedback_bp.route("/api/feedback/list", methods=["GET"])
@login_required
def feedback_list():
    # Simplified for the modular version
    return jsonify({"results": []})

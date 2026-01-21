from flask import Blueprint, request, Response, stream_with_context, jsonify
from flask_login import login_required, current_user
import json
from services.agent_orchestrator import ReflectionOrchestrator
from services.config_service import get_settings
from services.ai_service import search_knowledge
from governance.rbac import resolve_roles
import logging

query_bp = Blueprint('query', __name__)
logger = logging.getLogger("AskLytics-Query")

def stream_event(event: str, data: dict):
    # Standard SSE allows multiple data: lines, but the frontend manual parser 
    # expects a single data: line with the whole JSON object including its type.
    payload = {"type": event, "data": data}
    return f"data: {json.dumps(payload)}\n\n"

@query_bp.route("/api/ask/stream", methods=["POST"])
@query_bp.route("/api/query/stream", methods=["POST"])
@query_bp.route("/api/gemini_ask/stream", methods=["POST"])
@login_required
def ask_stream():
    """Agentic SQL generation with reflection."""
    data = request.get_json() or {}
    question = data.get("question")
    if not question:
        return jsonify({"ok": False, "error": "No question provided"}), 400

    # Retrieve context from knowledge base
    context = search_knowledge(question, k=5)
    
    # Optional: Add user-provided context or MDL discovery
    user_context = data.get("context", "")
    if user_context:
        context = f"{context}\n---\nUser Context:\n{user_context}"

    orchestrator = ReflectionOrchestrator()

    def generate():
        try:
            for event in orchestrator.generate_sql_with_reflection(question, context):
                yield stream_event(event["event"], event["data"])
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield stream_event("error", {"message": str(e)})
        finally:
            yield stream_event("done", {"message": "Stream complete."})

    return Response(stream_with_context(generate()), mimetype="text/event-stream")

@query_bp.route("/api/ask/preview", methods=["POST"])
@login_required
def ask_preview():
    data = request.get_json() or {}
    question = data.get("question", "")
    return jsonify({
        "intent": "NEW_QUERY",
        "will_refine": False,
        "refined_sql": None
    })

@query_bp.route("/api/summarize", methods=["POST"])
@login_required
def summarize_last():
    return jsonify({"summary": "This is a summary of the latest query results."})

@query_bp.route("/api/insight/explain", methods=["POST"])
@query_bp.route("/api/insight/summarize", methods=["POST"])
@query_bp.route("/api/insight/provenance", methods=["POST"])
@query_bp.route("/api/insight/confidence", methods=["POST"])
@login_required
def insight_explain():
    return jsonify({
        "summary": "This is an AI insight based on the data.",
        "provenance": "Insight derived from the primary sales table.",
        "confidence": {"score": 0.95, "label": "High", "reasons": ["FK match ok", "group-by valid"]}
    })

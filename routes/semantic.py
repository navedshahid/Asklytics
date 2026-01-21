from flask import Blueprint, request, jsonify
from flask_login import login_required
from pathlib import Path
import yaml
import logging
from services.discovery_agent import ScoutAgent

semantic_bp = Blueprint('semantic', __name__)
logger = logging.getLogger("AskLytics-Semantic")

BASE_DIR = Path("semantic/mdl")
ENTITIES_DIR = BASE_DIR / "entities"
RELATIONS_PATH = BASE_DIR / "relations.yaml"

ENTITIES_DIR.mkdir(parents=True, exist_ok=True)

@semantic_bp.route("/semantic/catalog", methods=["GET"])
@login_required
def get_catalog():
    req_type = request.args.get("type", "entity")
    if req_type == "entity":
        entities = []
        for p in ENTITIES_DIR.glob("*.yaml"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    entities.append({
                        "name": data.get("name"),
                        "description": data.get("description"),
                        "grain": data.get("grain", "primary"),
                        "columns": len(data.get("columns", []))
                    })
            except Exception as e:
                logger.error(f"Failed to load entity {p}: {e}")
        return jsonify({"entities": entities})
    return jsonify({"entities": []})

@semantic_bp.route("/semantic/entity/<name>", methods=["GET"])
@login_required
def get_entity_detail(name):
    path = ENTITIES_DIR / f"{name}.yaml"
    if not path.exists():
        return jsonify({"error": "Entity not found"}), 404
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@semantic_bp.route("/semantic/entities/<name>", methods=["DELETE"])
@login_required
def delete_entity(name):
    path = ENTITIES_DIR / f"{name}.yaml"
    if path.exists():
        path.unlink()
        return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404

@semantic_bp.route("/semantic/entities/import", methods=["POST"])
@login_required
def import_entities():
    data = request.get_json()
    tables = data.get("tables", [])
    if not tables:
        return jsonify({"error": "No tables selected"}), 400
    
    scout = ScoutAgent()
    # Modify ScoutAgent slightly to accept table list if needed, 
    # but for now it crawls everything in the schema.
    # We'll just run its discovery.
    result = scout.discover_and_generate() # It currently fetches all tables
    return jsonify(result)

@semantic_bp.route("/semantic/relations", methods=["GET", "POST"])
@login_required
def manage_relations():
    if request.method == "GET":
        if not RELATIONS_PATH.exists():
            return jsonify({"relations": []})
        try:
            with open(RELATIONS_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {"relations": []}
                return jsonify(data)
        except Exception as e:
            return jsonify({"relations": []})
    
    # POST
    new_rel = request.get_json()
    relations_data = {"relations": []}
    if RELATIONS_PATH.exists():
        try:
            with open(RELATIONS_PATH, "r", encoding="utf-8") as f:
                relations_data = yaml.safe_load(f) or {"relations": []}
        except: pass
    
    relations_data["relations"].append(new_rel)
    with open(RELATIONS_PATH, "w", encoding="utf-8") as f:
        yaml.dump(relations_data, f)
    return jsonify({"ok": True})

@semantic_bp.route("/semantic/relations/<name>", methods=["DELETE"])
@login_required
def delete_relation(name):
    if not RELATIONS_PATH.exists():
        return jsonify({"error": "Not found"}), 404
    try:
        with open(RELATIONS_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {"relations": []}
        
        original_len = len(data["relations"])
        data["relations"] = [r for r in data["relations"] if r.get("name") != name]
        
        if len(data["relations"]) == original_len:
            return jsonify({"error": "Not found"}), 404
            
        with open(RELATIONS_PATH, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

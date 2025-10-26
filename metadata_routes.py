# metadata_routes.py
from flask import Blueprint, request, jsonify
from metadata_store import (
    SessionLocal, init_db,
    upsert_asset, upsert_columns, publish_event,
    search_assets, get_asset_detail, list_sources
)

bp = Blueprint("metadata", __name__, url_prefix="/api/metadata")
init_db()  # idempotent

@bp.get("/assets")
def list_assets():
    """Lightweight search endpoint for the UI.

    Query params:
    - q: free text search over name/description/source
    - limit: max results (default 25)
    """
    q = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit") or 25)
    source = (request.args.get("source") or "").strip() or None
    active_only = (request.args.get("active") or "1") != "0"
    with SessionLocal() as s:
        rows = search_assets(s, q=q, limit=limit, source=source, active_only=active_only)
    return jsonify({"results": rows})

@bp.get("/assets/<int:asset_id>")
def asset_detail(asset_id: int):
    """Return a single asset with its column list for detail panes."""
    with SessionLocal() as s:
        data = get_asset_detail(s, asset_id)
    return (jsonify(data), 200) if data else (jsonify({"error": "Not found"}), 404)

@bp.post("/bulk_upsert")
def bulk_upsert():
    """Bulk insert/update of metadata rows.

    Body:
    - Array of objects: { "Asset": {...}, "Columns": [{...}] }

    Behavior:
    - Upserts asset and columns in a single transaction.
    - Emits a "schema.change" event for each asset to trigger downstream refresh.
    """
    payload = request.get_json(force=True) or []
    asset_ids = []
    with SessionLocal() as s:
        for item in payload:
            ad = item.get("Asset") or {}
            cols = item.get("Columns") or []
            asset_id = upsert_asset(s, ad)
            if cols: upsert_columns(s, asset_id, cols)
            asset_ids.append(asset_id)
            publish_event(s, "schema.change", {"asset_id": asset_id}, {"AssetId": asset_id})
        s.commit()
    return jsonify({"upserted": len(asset_ids), "asset_ids": asset_ids})

@bp.post("/events/publish")
def publish_generic():
    """Generic event publisher for ad-hoc testing/automation."""
    body = request.get_json(force=True) or {}
    topic = body.get("topic"); key = body.get("key") or {}; payload = body.get("payload") or {}
    if not topic: return jsonify({"error": "topic required"}), 400
    with SessionLocal() as s:
        kh = publish_event(s, topic, key, payload); s.commit()
    return jsonify({"ok": True, "key_hash": kh})

@bp.get("/sources")
def get_sources():
    """List distinct metadata sources (e.g., 'SqlServer:MyDB') for multi-source filtering."""
    with SessionLocal() as s:
        srcs = list_sources(s)
    return jsonify({"sources": srcs})

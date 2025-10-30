"""Governance / audit-related Flask blueprint."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from audit_logger import _db_path

AUDIT_ROOT = Path(__file__).resolve().parents[1]


def set_audit_root(root: Path | str) -> None:
    global AUDIT_ROOT
    AUDIT_ROOT = Path(root)


governance_bp = Blueprint("governance", __name__, url_prefix="/api/gov")


def _audit_db_file() -> Path:
    try:
        return _db_path(AUDIT_ROOT)
    except Exception:
        return AUDIT_ROOT / "data" / "audit.db"


def _query(conn: sqlite3.Connection, sql: str, *params: Any) -> List[sqlite3.Row]:
    cur = conn.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


@governance_bp.get("/audit/rollup")
def audit_rollup():
    """Return aggregated audit metrics for dashboards."""

    try:
        days = max(1, min(365, int(request.args.get("days", "30"))))
    except Exception:
        days = 30
    window_start = datetime.utcnow() - timedelta(days=days)

    db_file = _audit_db_file()
    if not db_file.exists():
        return jsonify({
            "window_days": days,
            "events": 0,
            "actions": [],
            "pii_exposures": 0,
            "total_cost_estimate": 0.0,
            "last_event_utc": None,
        })

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        since_iso = window_start.isoformat()
        event_rows = _query(
            conn,
            "SELECT action, COUNT(*) AS cnt FROM audit_events WHERE ts_utc >= ? GROUP BY action ORDER BY cnt DESC",
            since_iso,
        )
        events_total = sum(row["cnt"] for row in event_rows)
        pii_exposures = _query(
            conn,
            "SELECT COUNT(*) AS exposures FROM audit_events WHERE ts_utc >= ? AND masked = 0",
            since_iso,
        )[0]["exposures"]
        last_row = _query(conn, "SELECT ts_utc FROM audit_events ORDER BY ts_utc DESC LIMIT 1")
        last_event = last_row[0]["ts_utc"] if last_row else None

        cost_row = _query(
            conn,
            "SELECT COALESCE(SUM(token_cost_estimate), 0) AS total_cost FROM audit_log WHERE ts_utc >= ?",
            since_iso,
        )
        total_cost = float(cost_row[0]["total_cost"] if cost_row else 0.0)

        response: Dict[str, Any] = {
            "window_days": days,
            "events": int(events_total),
            "actions": [{"action": row["action"], "count": int(row["cnt"]) } for row in event_rows],
            "pii_exposures": int(pii_exposures),
            "total_cost_estimate": total_cost,
            "last_event_utc": last_event,
        }
        return jsonify(response)
    finally:
        conn.close()


@governance_bp.get("/audit/events")
def audit_events():
    """Return the most recent audit events (masked)."""

    try:
        limit = max(1, min(200, int(request.args.get("limit", "50"))))
    except Exception:
        limit = 50

    db_file = _audit_db_file()
    if not db_file.exists():
        return jsonify({"events": []})

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        rows = _query(
            conn,
            "SELECT ts_utc, user_hash, action, resource, masked, meta FROM audit_events ORDER BY ts_utc DESC LIMIT ?",
            limit,
        )
        events = [dict(row) for row in rows]
        return jsonify({"events": events})
    finally:
        conn.close()

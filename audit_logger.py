"""audit_logger.py

Lightweight audit logging for LLM interactions to support compliance and
traceability. Logs are stored in a local SQLite database for convenience
and exportable as CSV via the provided helper.

Schema (table: audit_log):
  id INTEGER PRIMARY KEY AUTOINCREMENT
  ts_utc TEXT ISO8601
  provider TEXT
  prompt_hash TEXT
  sql_hash TEXT
  feedback TEXT
  exec_time_ms INTEGER
  token_cost_estimate REAL

Sensitive value scrubbing removes obvious customer/vendor names by
heuristic patterns. Replace with more robust PII filters if required.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Iterable
import csv
import hashlib
import re
import sqlite3


@dataclass
class AuditRecord:
    ts_utc: str
    provider: str
    prompt_hash: str
    sql_hash: str
    feedback: str
    exec_time_ms: int
    token_cost_estimate: float


def _db_path(root: Path) -> Path:
    return root / "data" / "audit.db"


def _ensure_db(root: Path) -> None:
    p = _db_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    try:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc TEXT NOT NULL,
                provider TEXT,
                prompt_hash TEXT,
                sql_hash TEXT,
                feedback TEXT,
                exec_time_ms INTEGER,
                token_cost_estimate REAL
            )
            """
        )
        con.commit()
    finally:
        con.close()


def _ensure_validation_table(root: Path) -> None:
    p = _db_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    try:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_validation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc TEXT NOT NULL,
                action TEXT NOT NULL,
                score REAL,
                label TEXT,
                semantic_conf REAL
            )
            """
        )
        con.commit()
    finally:
        con.close()


def _ensure_events_table(root: Path | None) -> None:
    p = _db_path(root or Path('.'))
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    try:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc TEXT NOT NULL,
                user_hash TEXT,
                action TEXT NOT NULL,
                resource TEXT,
                masked INTEGER DEFAULT 1,
                meta TEXT
            )
            """
        )
        con.commit()
    finally:
        con.close()


def _hash(text: Optional[str]) -> str:
    if not text:
        return ""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _scrub(text: Optional[str]) -> str:
    if not text:
        return ""
    # Basic scrubbing for Customer/Vendor names (replace tokens)
    out = re.sub(r"(?i)Cust(Name)?\s*[:=]\s*'[^']+'", "CustName:'***'", text)
    out = re.sub(r"(?i)Vend(Name)?\s*[:=]\s*'[^']+'", "VendName:'***'", out)
    return out


def estimate_token_cost(prompt: str, model: str = "gemini-1.5-flash-latest") -> float:
    """Very rough cost estimate based on character count.

    Replace with provider pricing integration when available.
    """
    char_count = len(prompt or "")
    tokens = max(1, char_count // 4)
    # Assume $0.000002 per token as placeholder
    return round(tokens * 0.000002, 6)


def log_interaction(root: Path, provider: str, prompt: str, sql: str, feedback: str, exec_time_ms: int) -> None:
    """Persist a single audit record.

    Values are scrubbed and hashed as needed.
    """
    _ensure_db(root)
    p_hash = _hash(_scrub(prompt))
    s_hash = _hash(_scrub(sql))
    estimate = estimate_token_cost(prompt)
    con = sqlite3.connect(str(_db_path(root)))
    try:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO audit_log (ts_utc, provider, prompt_hash, sql_hash, feedback, exec_time_ms, token_cost_estimate) VALUES (?,?,?,?,?,?,?)",
            (
                datetime.utcnow().isoformat(),
                provider,
                p_hash,
                s_hash,
                feedback or "",
                int(exec_time_ms or 0),
                float(estimate),
            ),
        )
        con.commit()
    finally:
        con.close()


def log_validation_summary(root: Path, *, score: float, label: str, semantic_conf: float) -> None:
    """Persist a masked validation event. No raw SQL or prompt stored.

    ISO 27001: stores only anonymized summary fields.
    """
    _ensure_validation_table(root)
    con = sqlite3.connect(str(_db_path(root)))
    try:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO audit_validation (ts_utc, action, score, label, semantic_conf) VALUES (?,?,?,?,?)",
            (datetime.utcnow().isoformat(), "validation_complete", float(score), str(label or ""), float(semantic_conf or 0.0)),
        )
        con.commit()
    finally:
        con.close()


def export_last_30_days_csv(root: Path, out_file: Path) -> Path:
    """Export the last 30 days of audit logs as CSV and return the path."""
    _ensure_db(root)
    since = datetime.utcnow() - timedelta(days=30)
    rows: Iterable[tuple]
    con = sqlite3.connect(str(_db_path(root)))
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT ts_utc, provider, prompt_hash, sql_hash, feedback, exec_time_ms, token_cost_estimate FROM audit_log WHERE ts_utc >= ? ORDER BY ts_utc DESC",
            (since.isoformat(),),
        )
        rows = cur.fetchall()
    finally:
        con.close()

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ts_utc",
            "provider",
            "prompt_hash",
            "sql_hash",
            "feedback",
            "exec_time_ms",
            "token_cost_estimate",
        ])
        for r in rows:
            writer.writerow(list(r))
    return out_file


def log_event(root: Path | None, *, user_id: str, action: str, resource: str = "", masked: bool = True, meta: dict | None = None) -> None:
    """Generic masked audit event (e.g., feedback_submit)."""
    _ensure_events_table(root)
    con = sqlite3.connect(str(_db_path(root or Path('.'))))
    try:
        cur = con.cursor()
        user_hash = _hash(user_id) if masked else user_id
        cur.execute(
            "INSERT INTO audit_events (ts_utc, user_hash, action, resource, masked, meta) VALUES (?,?,?,?,?,?)",
            (datetime.utcnow().isoformat(), user_hash, action, resource or "", 1 if masked else 0, _scrub(str(meta or {}))),
        )
        con.commit()
    finally:
        con.close()

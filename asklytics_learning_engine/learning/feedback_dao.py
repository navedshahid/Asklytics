from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


LEARN_DB_URL = os.getenv("LEARN_DB_URL", "sqlite:///./learning_store.db")
DB_PATH = LEARN_DB_URL.split("sqlite:///")[-1] if LEARN_DB_URL.startswith("sqlite") else "./learning_store.db"


def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
          id INTEGER PRIMARY KEY,
          ts DATETIME DEFAULT CURRENT_TIMESTAMP,
          xp_id INTEGER,
          user_id TEXT,
          verdict TEXT CHECK(verdict IN ('correct','incorrect')),
          comment TEXT,
          sql_hash TEXT,
          confidence REAL,
          masked BOOLEAN DEFAULT 1,
          retrain_used BOOLEAN DEFAULT 0
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_feedback_xp ON feedback(xp_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_feedback_ts ON feedback(ts)")
    return con


def _hash_user(user_id: str) -> str:
    return hashlib.sha1((user_id or "").encode("utf-8")).hexdigest()


def save_feedback(xp_id: int, user_id: str, verdict: str, comment: Optional[str], sql_hash: str, confidence: Optional[float], masked: bool = True) -> int:
    con = _conn()
    try:
        uid = _hash_user(user_id) if masked else user_id
        cur = con.execute(
            "INSERT INTO feedback (xp_id,user_id,verdict,comment,sql_hash,confidence,masked) VALUES (?,?,?,?,?,?,?)",
            (int(xp_id), uid, verdict, comment or "", sql_hash, float(confidence) if confidence is not None else None, 1 if masked else 0),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def mark_retrain_used(feedback_id: int) -> None:
    con = _conn()
    try:
        con.execute("UPDATE feedback SET retrain_used=1 WHERE id=?", (int(feedback_id),))
        con.commit()
    finally:
        con.close()


def summary(days: int = 30) -> Dict[str, Any]:
    con = _conn()
    try:
        since = (datetime.utcnow() - timedelta(days=int(days))).isoformat(timespec="seconds")
        rows = con.execute("SELECT verdict, COUNT(1) FROM feedback WHERE ts >= ? GROUP BY verdict", (since,)).fetchall()
        totals = {r[0]: int(r[1]) for r in rows}
        correct = int(totals.get("correct", 0))
        incorrect = int(totals.get("incorrect", 0))
        total = correct + incorrect
        acc = (correct / total) if total else 0.0
        return {"total": total, "correct": correct, "incorrect": incorrect, "accuracy": round(acc, 4)}
    finally:
        con.close()


def list_feedback(limit: int = 50) -> List[Dict[str, Any]]:
    con = _conn()
    try:
        rows = con.execute(
            "SELECT id,ts,xp_id,user_id,verdict,substr(comment,1,200),sql_hash,confidence,masked,retrain_used FROM feedback ORDER BY ts DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": int(r[0]),
                "ts": r[1],
                "xp_id": int(r[2]) if r[2] is not None else None,
                "user_id": r[3],
                "verdict": r[4],
                "comment": r[5] or "",
                "sql_hash": r[6] or "",
                "confidence": float(r[7]) if r[7] is not None else None,
                "masked": bool(r[8]),
                "retrain_used": bool(r[9]),
            })
        return out
    finally:
        con.close()


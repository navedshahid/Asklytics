from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Tuple

LEARN_DB_URL = os.getenv("LEARN_DB_URL", "sqlite:///./learning_store.db")
DB_PATH = LEARN_DB_URL.split("sqlite:///")[-1] if LEARN_DB_URL.startswith("sqlite") else "./learning_store.db"


def _migrate(con: sqlite3.Connection) -> None:
    cur = con.execute("PRAGMA table_info('xp')")
    cols = {r[1] for r in cur.fetchall()}
    if "exec_ms" not in cols:
        con.execute("ALTER TABLE xp ADD COLUMN exec_ms REAL")
    if "error_type" not in cols:
        con.execute("ALTER TABLE xp ADD COLUMN error_type TEXT")
    if "tables_used" not in cols:
        con.execute("ALTER TABLE xp ADD COLUMN tables_used TEXT")
    if "joins" not in cols:
        con.execute("ALTER TABLE xp ADD COLUMN joins TEXT")
    # Hybrid validator additions
    if "validation_signals" not in cols:
        con.execute("ALTER TABLE xp ADD COLUMN validation_signals TEXT DEFAULT '{}' ")
    if "confidence_score" not in cols:
        con.execute("ALTER TABLE xp ADD COLUMN confidence_score REAL DEFAULT 0.0")
    if "confidence_label" not in cols:
        con.execute("ALTER TABLE xp ADD COLUMN confidence_label TEXT DEFAULT 'Low'")


@contextmanager
def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS xp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_prompt TEXT NOT NULL,
                generated_sql TEXT,
                validated_sql TEXT,
                schema_context TEXT,
                result_signature TEXT,
                score REAL,
                success INTEGER,
                feedback TEXT,
                provider TEXT,
                timestamp TEXT NOT NULL
            )
            """
        )
        _migrate(con)
        yield con
        con.commit()
    finally:
        con.close()


@dataclass
class Experience:
    id: int
    user_prompt: str
    generated_sql: Optional[str]
    validated_sql: Optional[str]
    schema_context: Optional[str]
    result_signature: Optional[str]
    score: Optional[float]
    success: Optional[bool]
    feedback: Optional[str]
    provider: Optional[str]
    timestamp: str
    exec_ms: Optional[float] = None
    error_type: Optional[str] = None
    tables_used: Optional[str] = None
    joins: Optional[str] = None
    validation_signals: Optional[str] = None
    confidence_score: Optional[float] = None
    confidence_label: Optional[str] = None


def save_experience(
    user_prompt: str,
    generated_sql: Optional[str] = None,
    validated_sql: Optional[str] = None,
    schema_context: Optional[str] = None,
    result_signature: Optional[str] = None,
    score: Optional[float] = None,
    success: Optional[bool] = None,
    feedback: Optional[str] = None,
    provider: Optional[str] = None,
    *,
    exec_ms: Optional[float] = None,
    error_type: Optional[str] = None,
    tables_used: Optional[str] = None,
    joins: Optional[str] = None,
    validation_signals: Optional[str] = None,
    confidence_score: Optional[float] = None,
    confidence_label: Optional[str] = None,
) -> int:
    """Persist a single experience row and return the new id."""
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with _conn() as con:
        info = con.execute("PRAGMA table_info('xp')").fetchall()
        cols = {r[1] for r in info}
        base_cols = [
            "user_prompt","generated_sql","validated_sql","schema_context",
            "result_signature","score","success","feedback","provider","timestamp"
        ]
        base_vals = [
            user_prompt, generated_sql, validated_sql, schema_context,
            result_signature, score, int(success) if success is not None else None,
            feedback, provider, ts,
        ]
        extra_cols = []
        extra_vals = []
        if "exec_ms" in cols:
            extra_cols.append("exec_ms"); extra_vals.append(exec_ms)
        if "error_type" in cols:
            extra_cols.append("error_type"); extra_vals.append(error_type)
        if "tables_used" in cols:
            extra_cols.append("tables_used"); extra_vals.append(tables_used)
        if "joins" in cols:
            extra_cols.append("joins"); extra_vals.append(joins)
        if "validation_signals" in cols:
            extra_cols.append("validation_signals"); extra_vals.append(validation_signals)
        if "confidence_score" in cols:
            extra_cols.append("confidence_score"); extra_vals.append(confidence_score)
        if "confidence_label" in cols:
            extra_cols.append("confidence_label"); extra_vals.append(confidence_label)
        names = ",".join(base_cols + extra_cols)
        placeholders = ",".join(["?"] * (len(base_vals) + len(extra_vals)))
        cur = con.execute(f"INSERT INTO xp({names}) VALUES ({placeholders})", base_vals + extra_vals)
        return int(cur.lastrowid)


def _rows_to_xp(rows: Iterable[Tuple]) -> List[Experience]:
    out: List[Experience] = []
    for r in rows:
        # Backward-compatible mapping with optional telemetry columns
        exp = Experience(
            id=r[0], user_prompt=r[1], generated_sql=r[2], validated_sql=r[3],
            schema_context=r[4], result_signature=r[5], score=r[6],
            success=bool(r[7]) if r[7] is not None else None, feedback=r[8],
            provider=r[9], timestamp=r[10]
        )
        if len(r) >= 15:
            exp.exec_ms = r[11]; exp.error_type = r[12]; exp.tables_used = r[13]; exp.joins = r[14]
        # Attempt to map new fields by column presence if available
        try:
            if len(r) >= 18:
                exp.validation_signals = r[15]
                exp.confidence_score = r[16]
                exp.confidence_label = r[17]
        except Exception:
            pass
        out.append(exp)
    return out


def get_all_experiences(limit: Optional[int] = None) -> List[Experience]:
    with _conn() as con:
        q = (
            "SELECT id,user_prompt,generated_sql,validated_sql,schema_context,result_signature,"
            "score,success,feedback,provider,timestamp,exec_ms,error_type,tables_used,joins,"
            "validation_signals,confidence_score,confidence_label FROM xp ORDER BY id DESC"
        )
        if limit:
            q += f" LIMIT {int(limit)}"
        rows = con.execute(q).fetchall()
        return _rows_to_xp(rows)


def fetch_similar_examples(prompt: str, k: int = 3) -> List[Experience]:
    """Simple lexical fallback (BM25-like) if FAISS is unavailable.

    The embedder module should be used for real retrieval; this function is a
    safe fallback when embeddings/index are not yet built.
    """
    terms = set((prompt or "").lower().split())
    with _conn() as con:
        rows = con.execute(
            "SELECT id,user_prompt,generated_sql,validated_sql,schema_context,result_signature,score,success,feedback,provider,timestamp,exec_ms,error_type,tables_used,joins FROM xp"
        ).fetchall()
    scored: List[Tuple[float, Experience]] = []
    for xp in _rows_to_xp(rows):
        text = f"{xp.user_prompt} {xp.generated_sql or ''} {xp.validated_sql or ''}".lower()
        overlap = sum(1 for t in terms if t in text)
        scored.append((overlap, xp))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [xp for _, xp in scored[:k]]


def count_experiences() -> int:
    """Count total number of experiences in the store."""
    with _conn() as con:
        result = con.execute("SELECT COUNT(*) FROM xp").fetchone()
        return result[0] if result else 0


def validate_experiences() -> int:
    """Validate experience store integrity and return count of valid experiences."""
    with _conn() as con:
        # Check for experiences with valid data
        result = con.execute("""
            SELECT COUNT(*) FROM xp 
            WHERE user_prompt IS NOT NULL 
            AND user_prompt != ''
            AND (generated_sql IS NOT NULL OR validated_sql IS NOT NULL)
        """).fetchone()
        return result[0] if result else 0


def cleanup_old_data(days: int = 90) -> int:
    """Clean up old experiences older than specified days."""
    with _conn() as con:
        result = con.execute("""
            DELETE FROM xp 
            WHERE timestamp < datetime('now', '-{} days')
        """.format(days))
        return result.rowcount


def clear_experiences() -> int:
    """Clear all experiences from the store."""
    with _conn() as con:
        result = con.execute("DELETE FROM xp")
        return result.rowcount


def get_metrics_summary() -> dict:
    """Get summary metrics for the experience store."""
    with _conn() as con:
        # Total experiences
        total = con.execute("SELECT COUNT(*) FROM xp").fetchone()[0]
        
        # Successful experiences
        successful = con.execute("SELECT COUNT(*) FROM xp WHERE success = 1").fetchone()[0]
        
        # Average score
        avg_score = con.execute("SELECT AVG(score) FROM xp WHERE score IS NOT NULL").fetchone()[0]
        avg_score = avg_score if avg_score is not None else 0.0
        
        # Average confidence
        avg_confidence = con.execute("SELECT AVG(confidence_score) FROM xp WHERE confidence_score IS NOT NULL").fetchone()[0]
        avg_confidence = avg_confidence if avg_confidence is not None else 0.0
        
        return {
            "total_experiences": total,
            "successful_experiences": successful,
            "success_rate": successful / total if total > 0 else 0.0,
            "average_score": avg_score,
            "average_confidence": avg_confidence
        }

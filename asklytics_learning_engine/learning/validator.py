from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import sqlparse  # type: ignore

try:
    # New hybrid validator (rule+semantic+shadow). Shadow path requires a DB conn; not used here.
    from .hybrid_validator import validate as hybrid_validate  # type: ignore
except Exception:
    hybrid_validate = None  # type: ignore

try:
    # Use existing app metadata models for real checks
    from metadata_store import SessionLocal, Asset, ColumnDef  # type: ignore
except Exception:
    SessionLocal = None  # type: ignore
    Asset = None  # type: ignore
    ColumnDef = None  # type: ignore


_DANGEROUS = re.compile(r"\b(DELETE|UPDATE|INSERT|MERGE|DROP|ALTER|TRUNCATE)\b", re.IGNORECASE)
_SELECT = re.compile(r"^\s*SELECT\b", re.IGNORECASE | re.DOTALL)
_TOP = re.compile(r"\bSELECT\s+TOP\s*\(\d+\)\b", re.IGNORECASE)


@dataclass
class ValidationResult:
    ok: bool
    errors: List[str]
    warnings: List[str]
    score: float  # heuristic [0..1]
    safe_sql: str


def _ensure_preview_top(sql: str, top: int = 50) -> str:
    if not _SELECT.search(sql):
        return sql
    if _TOP.search(sql):
        return sql
    # naive but effective: inject TOP after SELECT
    return re.sub(r"(?is)^\s*select\s+", f"SELECT TOP ({top}) ", sql, count=1)


def _extract_tables(sql: str) -> List[str]:
    # capture [schema].[table] or schema.table or plain table after FROM/JOIN
    patt = re.compile(r"(?is)(?:from|join)\s+((?:\[?\w+\]?\.)?\[?\w+\]?)")
    found = patt.findall(sql or "")
    cleaned = []
    for t in found:
        x = t.strip(" []")
        if "." not in x:
            cleaned.append(f"dbo.{x}")
        else:
            cleaned.append(x.replace("[", "").replace("]", ""))
    return list(dict.fromkeys(cleaned))  # unique, preserve order


def _check_exists(tables: List[str]) -> Dict[str, bool]:
    if SessionLocal is None or Asset is None:
        return {t: True for t in tables}  # cannot verify; assume true
    okmap: Dict[str, bool] = {}
    with SessionLocal() as s:  # type: ignore
        for t in tables:
            sch, name = (t.split(".", 1) + [""])[:2]
            row = (
                s.query(Asset)
                .filter(Asset.SchemaName == sch, Asset.ObjectName == name, Asset.IsActive.is_(True))
                .one_or_none()
            )
            okmap[t] = bool(row)
    return okmap


def validate_sql(sql: str, schema_context: Optional[str] = None) -> ValidationResult:
    errs: List[str] = []
    warns: List[str] = []
    if _DANGEROUS.search(sql or ""):
        errs.append("Dangerous statement detected (DDL/DML blocked).")

    try:
        parsed = sqlparse.parse(sql or "")
        if not parsed:
            errs.append("Empty or unparsable SQL.")
    except Exception:
        errs.append("SQL parsing failed.")

    tables = _extract_tables(sql or "")
    exists = _check_exists(tables)
    missing = [t for t, ok in exists.items() if not ok]
    if missing:
        warns.append(f"Unknown tables: {', '.join(missing)}")

    safe_sql = _ensure_preview_top(sql or "")

    # Default structural score
    structural = 1.0 - (1.0 if errs else 0.0) - (0.2 if _DANGEROUS.search(sql or "") else 0.0)
    semantic = 1.0 - (0.1 * len(missing))
    score = max(0.0, min(1.0, 0.6 * structural + 0.4 * semantic))

    # If hybrid validator is available, use its confidence score (without DB shadow here)
    try:
        if hybrid_validate:
            signals = hybrid_validate(sql, user_prompt="", schema=None, conn=None)  # type: ignore
            if isinstance(signals, dict) and "confidence_score" in signals:
                score = float(signals.get("confidence_score") or score)
    except Exception:
        pass

    return ValidationResult(ok=not errs, errors=errs, warnings=warns, score=score, safe_sql=safe_sql)

from __future__ import annotations

import re
import time
from typing import Dict, List, Tuple


_DANGEROUS = re.compile(r"\b(DELETE|UPDATE|INSERT|MERGE|DROP|ALTER|TRUNCATE)\b", re.IGNORECASE)
_SELECT = re.compile(r"^\s*SELECT\b", re.IGNORECASE | re.DOTALL)


def load_schema_metadata() -> Dict[str, List[str]]:
    """Return minimal schema map {"schema.table": [columns...]}. Safe for ISO 27001.

    Uses metadata_store if available; otherwise returns an empty map.
    """
    try:
        from metadata_store import SessionLocal, Asset, ColumnDef  # type: ignore
    except Exception:
        return {}
    out: Dict[str, List[str]] = {}
    try:
        with SessionLocal() as s:  # type: ignore
            # Collect active assets
            assets = s.query(Asset).filter(Asset.IsActive.is_(True)).all()  # type: ignore
            ids = [a.AssetId for a in assets]
            col_rows = s.query(ColumnDef).filter(ColumnDef.AssetId.in_(ids)).all()  # type: ignore
            by_asset: Dict[int, List[str]] = {}
            for c in col_rows:
                by_asset.setdefault(int(c.AssetId), []).append(str(c.ColumnName))
            for a in assets:
                key = f"{a.SchemaName}.{a.ObjectName}" if a.SchemaName else str(a.ObjectName)
                out[key.lower()] = by_asset.get(int(a.AssetId), [])
    except Exception:
        return {}
    return out


def _extract_tables(sql: str) -> List[str]:
    patt = re.compile(r"(?is)(?:from|join)\s+((?:\[?\w+\]?\.)?\[?\w+\]?)")
    found = patt.findall(sql or "")
    cleaned = []
    for t in found:
        x = t.strip(" []")
        if x:
            cleaned.append(x.replace("[", "").replace("]", ""))
    # Normalize to schema.table when possible
    norm = []
    for x in cleaned:
        if "." not in x:
            norm.append(f"dbo.{x}")
        else:
            norm.append(x)
    # preserve order, unique
    seen = set()
    out: List[str] = []
    for t in norm:
        tl = t.lower()
        if tl not in seen:
            out.append(tl); seen.add(tl)
    return out


def validate_schema(sql: str) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    if not sql or not _SELECT.search(sql):
        errs.append("Not a SELECT statement")
    if _DANGEROUS.search(sql or ""):
        errs.append("Dangerous statement detected")
    # Very light parse check: must contain FROM
    if not re.search(r"(?i)\bFROM\b", sql or ""):
        errs.append("Missing FROM clause")
    return (len(errs) == 0), errs


def validate_joins(sql: str) -> Tuple[bool, List[str]]:
    """Heuristic FK validation.

    - If no JOIN present -> True
    - If JOIN present, require an ON with equality comparing dotted identifiers
    """
    jpat = re.compile(r"(?is)\bJOIN\b")
    if not jpat.search(sql or ""):
        return True, []
    # Require ON a.b = c.d
    on_ok = re.search(r"(?is)\bJOIN\b.*?\bON\b\s+\w+\.\w+\s*=\s*\w+\.\w+", sql)
    if on_ok:
        return True, []
    return False, ["JOIN without valid ON a.b = c.d"]


def detect_groupby_anomaly(sql: str, schema: Dict[str, List[str]] | None = None) -> bool:
    """Return True when aggregates detected without GROUP BY combining non-aggregates.

    NOTE: COUNT(*) alone is fine without GROUP BY.
    """
    if not sql:
        return False
    has_agg = bool(re.search(r"(?i)\b(SUM|AVG|MIN|MAX|COUNT)\s*\(", sql))
    if not has_agg:
        return False
    if re.search(r"(?i)COUNT\(\s*\*\s*\)", sql):
        # allow pure count(*)
        sel = re.search(r"(?is)SELECT\s+(.*?)\s+FROM", sql)
        if sel:
            seg = sel.group(1)
            # if selection has only COUNT(*) optionally aliased
            toks = [t.strip() for t in seg.split(',')]
            others = [t for t in toks if not re.search(r"(?i)^COUNT\(\s*\*\s*\)", t)]
            if not others:
                return False
    return not bool(re.search(r"(?i)\bGROUP\s+BY\b", sql))


def safe_sql(sql: str) -> bool:
    return not bool(_DANGEROUS.search(sql or ""))


def validate_all(sql: str, schema: Dict[str, List[str]] | None = None) -> Dict[str, object]:
    t0 = time.time()
    valid, schema_errors = validate_schema(sql)
    fk_ok, fk_missing = validate_joins(sql)
    grp_anom = detect_groupby_anomaly(sql, schema)
    latency_ms = int((time.time() - t0) * 1000)
    return {
        "valid_schema": bool(valid and not schema_errors),
        "schema_errors": schema_errors,
        "fk_ok": fk_ok,
        "missing_keys": fk_missing,
        "group_by_ok": not grp_anom,
        "latency_ms": latency_ms,
    }


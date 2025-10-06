# safety/schema_guard.py
import re
from typing import Dict, List, Set, Tuple

Ident = str

def _split_qualified(name: str) -> Tuple[str|None, str]:
    parts = name.split(".")
    if len(parts) == 2: return parts[0], parts[1]
    return None, parts[0]

def _extract_idents(sql: str) -> Tuple[Set[Ident], Set[Tuple[Ident, Ident]]]:
    """
    Very light parser:
      - finds schema.table tokens after FROM / JOIN
      - finds column tokens in SELECT list and predicates
    """
    s = " " + sql.lower() + " "
    tables: Set[Ident] = set()
    cols: Set[Tuple[Ident, Ident]] = set()

    # FROM/JOIN tables (schema.table or table)
    for m in re.finditer(r"\b(from|join)\s+([a-zA-Z0-9_\.]+)", s):
        tables.add(m.group(2))

    # Qualified columns like schema.table.col or table.col
    for m in re.finditer(r"\b([a-zA-Z0-9_\.]+)\s*\.\s*([a-zA-Z0-9_]+)", s):
        left, col = m.group(1), m.group(2)
        # left can be schema.table or alias; we only add if it looks like table-ish
        if "." in left:
            cols.add((left, col))
    return tables, cols

def _catalog_maps(retrieval: Dict) -> Tuple[Set[Ident], Dict[Ident, Set[str]]]:
    allowed_tables: Set[Ident] = set(retrieval.get("tables", []))
    allowed_cols: Dict[Ident, Set[str]] = {}
    for c in retrieval.get("columns", []):
        t = c["table"]
        allowed_cols.setdefault(t, set()).add(c["name"])
    return allowed_tables, allowed_cols

def validate_or_patch_sql(sql: str, retrieval: Dict) -> Tuple[bool, str, List[str]]:
    """
    Returns (ok, patched_sql_or_original, reasons)
    - ok=True: safe to run
    - ok=False: do not run; reasons contain user-friendly messages
    """
    allowed_tables, allowed_cols = _catalog_maps(retrieval)
    tables_used, cols_used = _extract_idents(sql)

    reasons: List[str] = []
    bad_tables: Set[Ident] = set()
    for t in tables_used:
        # normalize to schema.table if just table provided
        if "." not in t:
            # try to match any allowed table's short name
            matches = [at for at in allowed_tables if at.split(".", 1)[1] == t]
            if matches:
                # patch token with schema-qualified name
                sql = re.sub(rf"\b{re.escape(t)}\b", matches[0], sql, flags=re.IGNORECASE)
            else:
                bad_tables.add(t)
        else:
            if t not in allowed_tables:
                bad_tables.add(t)

    if bad_tables:
        reasons.append(f"Unknown/unauthorized tables: {', '.join(sorted(bad_tables))}")

    bad_cols: List[str] = []
    for t, col in cols_used:
        # try resolving short table name first
        if "." not in t:
            matches = [at for at in allowed_tables if at.split(".",1)[1] == t]
            t_full = matches[0] if matches else t
        else:
            t_full = t
        if t_full not in allowed_cols or col not in allowed_cols.get(t_full, set()):
            bad_cols.append(f"{t}.{col}")

    if bad_cols:
        reasons.append(f"Unknown columns: {', '.join(sorted(bad_cols))}")

    if reasons:
        # If the query is a simple SELECT list, try auto-fix by dropping unknown columns
        if bad_cols and "select" in sql.lower():
            for bad in bad_cols:
                # remove patterns like ", t.col" or "t.col," or "t.col"
                name = bad.split(".",1)[1] if "." in bad else bad
                sql = re.sub(rf"\s*,\s*\b{re.escape(name)}\b", "", sql, flags=re.IGNORECASE)
                sql = re.sub(rf"\b{re.escape(name)}\b\s*,\s*", "", sql, flags=re.IGNORECASE)
        # Re-check columns after pruning
        _, cols_used2 = _extract_idents(sql)
        still_bad = []
        for t, col in cols_used2:
            t_full = t if "." in t else next((at for at in allowed_tables if at.split(".",1)[1] == t), t)
            if t_full not in allowed_cols or col not in allowed_cols.get(t_full, set()):
                still_bad.append(f"{t}.{col}")

        if bad_tables or still_bad:
            return False, sql, reasons

    return True, sql, []

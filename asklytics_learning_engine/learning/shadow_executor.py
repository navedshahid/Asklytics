from __future__ import annotations

from typing import Dict


def shadow_validate(sql: str, conn) -> Dict[str, object]:
    """
    Runs simplified aggregate checks without inspecting PII: COUNT(*) over the query.
    Returns {"non_empty": bool, "rowcount": int, "agg_checks": {...}}

    - Uses a subquery SELECT COUNT(*) FROM (sql) t
    - Does not read any data values or PII columns
    """
    out = {"non_empty": False, "rowcount": 0, "agg_checks": {}}
    if not sql or conn is None:
        return out
    try:
        q = f"SELECT COUNT(*) AS c FROM ({sql}) AS t"
        cur = conn.cursor()
        cur.execute(q)
        row = cur.fetchone()
        cnt = int(row[0]) if row and row[0] is not None else 0
        out["rowcount"] = cnt
        out["non_empty"] = bool(cnt > 0)
    except Exception:
        # Non-fatal
        return out
    return out


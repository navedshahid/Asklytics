from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Sequence


def result_signature(rows: Sequence[Dict[str, Any]] | None, max_rows: int = 10) -> str:
    """Compute a stable signature to summarize results for learning.

    Uses top-N rows and ordered keys to hash a compact fingerprint.
    """
    if not rows:
        return "empty:0"
    take = rows[:max_rows]
    parts: List[str] = []
    for r in take:
        keys = sorted(r.keys())
        vals = [str(r.get(k)) for k in keys]
        parts.append("|".join([";".join(keys), ":".join(vals)]))
    blob = "\n".join(parts).encode("utf-8", errors="ignore")
    return hashlib.sha1(blob).hexdigest()


def combine_context(prompt: str, schema_ctx: str, examples: Sequence[Dict[str, str]]) -> str:
    """Merge schema context and few-shot examples into a single prompt preamble."""
    few_shot = []
    for ex in examples:
        p = ex.get("user_prompt") or ""
        s = ex.get("validated_sql") or ex.get("generated_sql") or ""
        if not p or not s:
            continue
        few_shot.append(f"-- Example\n-- Q: {p}\n{str(s).strip()}\n")
    fs = "\n".join(few_shot[:3])
    return (f"-- Schema Context\n{schema_ctx}\n\n{fs}").strip()


from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import experience_store as xp
from .embedder import embed_text, query_faiss
from .gemini_wrapper import GeminiWrapper
from .metrics import combine_context, result_signature
from .validator import ValidationResult, validate_sql


# Optional DB execution using pyodbc if available
def _try_execute(sql: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    try:
        import pyodbc  # type: ignore
    except Exception:
        return [], []

    conn_str = os.getenv("ASKLYTICS_ODBC_DSN") or os.getenv("ASKLYTICS_ODBC_CONNSTR")
    if not conn_str:
        return [], []
    with pyodbc.connect(conn_str, timeout=10) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return cols, rows


def _compute_score(v: ValidationResult, rows: Sequence[Dict[str, Any]]) -> float:
    structural = v.score
    semantic = 1.0 if rows else 0.0
    return 0.6 * structural + 0.4 * semantic


def _to_example_dict(exps: Sequence[xp.Experience]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for e in exps:
        out.append({
            "user_prompt": e.user_prompt,
            "generated_sql": e.generated_sql or "",
            "validated_sql": e.validated_sql or "",
        })
    return out


def _retrieve_examples(prompt: str, k: int) -> List[xp.Experience]:
    # Try FAISS first
    try:
        vec = embed_text(prompt)
        ids = query_faiss(vec, k=k)
        if ids:
            all_xp = xp.get_all_experiences()
            by_id = {e.id: e for e in all_xp}
            return [by_id[i] for i in ids if i in by_id]
    except Exception:
        pass
    # Fallback lexical
    return xp.fetch_similar_examples(prompt, k)


def process_query(prompt: str, schema_ctx: str = "", provider: str = "gemini") -> Tuple[str, List[Dict[str, Any]], float]:
    examples = _retrieve_examples(prompt, k=int(os.getenv("LEARN_TOPK", "3")))
    context = combine_context(prompt, schema_ctx, _to_example_dict(examples))

    # Candidate generation
    gw = GeminiWrapper()
    candidates: List[str] = []
    for _ in range(3):
        sql = gw.generate_sql(prompt, context)
        # strip code fences if any
        m = re.search(r"```(?:sql\s*)?(.*?)```", sql, re.DOTALL | re.IGNORECASE)
        sql = (m.group(1) if m else sql).strip().rstrip(";")
        candidates.append(sql)

    scored: List[Tuple[float, str, List[Dict[str, Any]], ValidationResult]] = []
    for sql in candidates:
        v = validate_sql(sql, schema_ctx)
        cols, rows = _try_execute(v.safe_sql)
        s = _compute_score(v, rows)
        scored.append((s, v.safe_sql, rows, v))

    best = max(scored, key=lambda x: x[0]) if scored else (0.0, "", [], ValidationResult(False, [], [], 0.0, ""))
    best_score, best_sql, best_rows, best_v = best
    sig = result_signature(best_rows)
    xp.save_experience(
        user_prompt=prompt,
        generated_sql=best_sql,
        validated_sql=best_sql if best_v.ok else None,
        schema_context=schema_ctx,
        result_signature=sig,
        score=best_score,
        success=True if best_rows else False,
        feedback=None,
        provider=provider,
    )
    return best_sql, best_rows, best_score


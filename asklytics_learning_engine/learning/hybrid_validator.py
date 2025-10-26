from __future__ import annotations

from typing import Dict, Tuple

from . import validation_rules
from . import semantic_reviewer
from . import shadow_executor

try:
    # prefer installed services path
    from services import confidence_scorer  # type: ignore
except Exception:  # fallback for alternative layouts
    import importlib
    confidence_scorer = importlib.import_module('services.confidence_scorer')  # type: ignore


def validate(sql: str, user_prompt: str, schema: dict | None, conn) -> Dict[str, object]:
    rules = validation_rules.validate_all(sql, schema)
    semantic = semantic_reviewer.review_sql_intent(sql, user_prompt, schema)
    shadow = shadow_executor.shadow_validate(sql, conn)
    signals: Dict[str, object] = {
        "valid_schema": bool(rules.get("valid_schema")),
        "fk_ok": bool(rules.get("fk_ok")),
        "group_by_ok": bool(rules.get("group_by_ok")),
        "semantic_match": bool(semantic.get("semantic_match")),
        "semantic_confidence": float(semantic.get("confidence") or 0.0),
        "non_empty": bool(shadow.get("non_empty")),
        "rowcount": int(shadow.get("rowcount") or 0),
        "latency_ms": int(rules.get("latency_ms") or 0),
    }
    score, label = confidence_scorer.compute(signals)
    signals["confidence_score"] = score
    signals["confidence_label"] = label
    return signals


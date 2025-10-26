from __future__ import annotations

from typing import Dict, Tuple


def compute(signals: Dict[str, object]) -> Tuple[float, str]:
    score = 0.4
    if signals.get("valid_schema"):
        score += 0.2
    if signals.get("fk_ok"):
        score += 0.1
    if signals.get("semantic_match"):
        score += 0.15
    if signals.get("non_empty"):
        score += 0.1
    try:
        lat = float(signals.get("latency_ms", 1000) or 1000)
    except Exception:
        lat = 1000
    if lat < 1000:
        score += 0.05
    score = max(0.0, min(float(score), 1.0))
    label = "High" if score >= 0.8 else ("Medium" if score >= 0.6 else "Low")
    return score, label


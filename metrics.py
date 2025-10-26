"""metrics.py

Utility functions to compute ROI and quality metrics for AskLytics.

The functions here intentionally avoid tight coupling to the learning
engine. When the optional `asklytics_learning_engine` package is
available, we call into it; otherwise we compute conservative fallbacks.

All functions are safe to import even if dependencies are missing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import json


@dataclass
class SummaryMetrics:
    """Aggregate KPI-style metrics for the dashboard."""

    total_queries: int = 0
    average_accuracy: float = 0.0
    average_correction_rate: float = 0.0
    time_saved_ms_est: int = 0
    last_updated: Optional[str] = None


def _get_learning_eval():
    """Best-effort import of learning evaluation service."""
    try:
        from asklytics_learning_engine.learning import eval_service as learn_eval  # type: ignore
        return learn_eval
    except Exception:
        return None


def compute_summary(default_manual_ms: int = 300000, default_ai_ms: int = 30000) -> SummaryMetrics:
    """Compute dashboard summary.

    - total_queries: count of experiences in the learning store
    - average_accuracy: from rolling accuracy
    - average_correction_rate: 1 - accuracy as a simple proxy
    - time_saved_ms_est: naive estimate using provided defaults
    - last_updated: ISO timestamp from learning store if available
    """
    eval_mod = _get_learning_eval()

    if not eval_mod:
        return SummaryMetrics(
            total_queries=0,
            average_accuracy=0.0,
            average_correction_rate=0.0,
            time_saved_ms_est=max(0, default_manual_ms - default_ai_ms),
            last_updated=None,
        )

    try:
        size = eval_mod.size_and_growth()
        roll = eval_mod.rolling_accuracy(30)
        total = int(size.get("xp_total", 0))
        acc = float(roll.get("accuracy", 0.0))
        last_ts = size.get("last_updated")
        if isinstance(last_ts, (int, float)):
            last = datetime.utcfromtimestamp(last_ts).isoformat()
        elif isinstance(last_ts, str):
            last = last_ts
        else:
            last = None
        avg_corr = max(0.0, min(1.0, 1.0 - acc))
        time_saved = max(0, default_manual_ms - default_ai_ms) * total
        return SummaryMetrics(
            total_queries=total,
            average_accuracy=acc,
            average_correction_rate=avg_corr,
            time_saved_ms_est=time_saved,
            last_updated=last,
        )
    except Exception:
        return SummaryMetrics(
            total_queries=0,
            average_accuracy=0.0,
            average_correction_rate=0.0,
            time_saved_ms_est=max(0, default_manual_ms - default_ai_ms),
            last_updated=None,
        )


def persist_regression_result(result: Dict[str, Any], root: Path) -> Path:
    """Persist a regression run under data/regression/YYYY-MM-DD.json.

    Returns the written file path.
    """
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    out_dir = root / "data" / "regression"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{date_str}.json"
    try:
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    except Exception:
        # Best-effort; ignore persistence failures for now
        pass
    return out_file


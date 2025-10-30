from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Tuple

try:
    from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
except ImportError:
    BackgroundScheduler = None

from . import experience_store as xp
from .embedder import build_faiss_index


logger = logging.getLogger("learning.nightly")


def _collect_pairs() -> List[Tuple[int, str]]:
    """Prepare (xp_id, text) pairs for embedding.

    We blend prompt + validated_sql + schema_context for richer vectors.
    """
    pairs: List[Tuple[int, str]] = []
    for e in xp.get_all_experiences():
        text = f"Prompt: {e.user_prompt}\nSQL: {e.validated_sql or e.generated_sql or ''}\nContext: {e.schema_context or ''}"
        pairs.append((e.id, text))
    return pairs


def recompute_indices():
    pairs = _collect_pairs()
    build_faiss_index(pairs)


def recompute_accuracy():
    """Compute coarse accuracy metrics; placeholder for dashboards."""
    exps = xp.get_all_experiences(limit=1000)
    total = len(exps)
    success = sum(1 for e in exps if (e.success or 0))
    logger.info("[nightly] accuracy: %.2f (%d/%d)", (success / total * 100.0) if total else 0.0, success, total)


def identify_low_accuracy_components():
    # Placeholder: scan feedback for repeated tables/joins; return future work list
    return []


def run_all_jobs():
    recompute_accuracy()
    identify_low_accuracy_components()
    recompute_indices()


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler()
    # Run nightly at 02:15
    sched.add_job(run_all_jobs, "cron", hour=2, minute=15, id="learning_nightly")
    sched.start()
    logger.info("Learning nightly job scheduled (02:15)")
    return sched


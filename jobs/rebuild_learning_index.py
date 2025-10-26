"""jobs/rebuild_learning_index.py

Nightly job to maintain the learning store and FAISS index.
This module is safe to import even if the learning engine is absent.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def run(root: Path) -> dict:
    """Run maintenance tasks and return a summary dict."""
    kept = removed = 0
    avg_score = 0.0
    actions: list[str] = []

    try:
        from asklytics_learning_engine.learning import experience_store as xp  # type: ignore
        actions.append("experience_store:available")
        try:
            removed = int(xp.prune_low_score_examples(threshold=0.5) or 0)
            actions.append(f"pruned:{removed}")
        except Exception:
            actions.append("prune:failed")
        try:
            stats = xp.compute_stats()
            kept = int(stats.get("count", 0))
            avg_score = float(stats.get("avg_score", 0.0))
            actions.append("stats:ok")
        except Exception:
            actions.append("stats:failed")
    except Exception:
        actions.append("experience_store:missing")

    try:
        from asklytics_learning_engine.learning.nightly_job import recompute_indices as learn_reindex  # type: ignore
        learn_reindex()
        actions.append("reindex:ok")
    except Exception:
        actions.append("reindex:missing_or_failed")

    # Vacuum/compact SQLite metadata DB if present
    try:
        import sqlite3
        db = root / "metadata.db"
        if db.exists():
            con = sqlite3.connect(str(db))
            try:
                con.execute("VACUUM")
            finally:
                con.close()
            actions.append("vacuum:metadata_db")
    except Exception:
        actions.append("vacuum:failed")

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "kept": kept,
        "removed": removed,
        "avg_score": avg_score,
        "actions": actions,
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    out = run(root)
    print(out)


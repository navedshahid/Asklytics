from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
import sys


def main():
    # Ensure local package imports work
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    # Ensure XP store exists and migrations run by saving a row
    try:
        from asklytics_learning_engine.learning import experience_store as xp
    except Exception as e:
        print("ERR: cannot import experience_store:", e)
        return 1

    # Insert a sample with confidence fields
    row_id = xp.save_experience(
        user_prompt="health check",
        generated_sql="SELECT 1 as a",
        validated_sql="SELECT 1 as a",
        schema_context=None,
        result_signature=None,
        score=0.7,
        success=True,
        feedback=None,
        provider="check",
        exec_ms=5.0,
        validation_signals=json.dumps({"valid_schema": True, "fk_ok": True, "non_empty": True, "confidence_score": 0.72, "confidence_label": "Medium"}),
        confidence_score=0.72,
        confidence_label="Medium",
    )
    print("Inserted row id:", row_id)

    # Inspect columns
    db_url = os.getenv("LEARN_DB_URL", "sqlite:///./learning_store.db")
    db_path = db_url.split("sqlite:///")[-1]
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute("PRAGMA table_info('xp')")
        cols = [r[1] for r in cur.fetchall()]
    finally:
        con.close()
    print("XP columns:", cols)

    # ROI metrics
    try:
        from roi import metrics_service as roi
    except Exception as e:
        print("ROI import error:", e)
        return 0

    avg = roi.avg_confidence(365)
    trend = roi.weekly_confidence_trend(2)
    kpi = roi.accuracy_kpi_confident(0.8, 365)
    print("avg_confidence(365)=", avg)
    print("weekly_confidence_trend(2)=", trend)
    print("accuracy_kpi_confident(0.8,365)=", kpi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

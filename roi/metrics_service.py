from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List


DB_PATH = os.getenv("LEARN_DB_URL", "sqlite:///./learning_store.db").split("sqlite:///")[-1]


def _conn():
    return sqlite3.connect(DB_PATH)


def avg_confidence(days: int = 30) -> float:
    since = (datetime.utcnow() - timedelta(days=int(days))).isoformat(timespec="seconds")
    try:
        with _conn() as con:
            cur = con.execute(
                "SELECT AVG(confidence_score) FROM xp WHERE timestamp >= ?",
                (since,),
            )
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
    except Exception:
        return 0.0


def weekly_confidence_trend(weeks: int = 8) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    try:
        with _conn() as con:
            for i in range(weeks):
                end = datetime.utcnow() - timedelta(weeks=i)
                start = end - timedelta(weeks=1)
                cur = con.execute(
                    "SELECT AVG(confidence_score) FROM xp WHERE timestamp >= ? AND timestamp < ?",
                    (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
                )
                row = cur.fetchone()
                out.append({
                    "week_start": start.date().isoformat(),
                    "avg_confidence": float(row[0]) if row and row[0] is not None else 0.0,
                })
    except Exception:
        pass
    out.reverse()
    return out


def accuracy_kpi_confident(threshold: float = 0.8, days: int = 30) -> float:
    """Percentage of queries with confidence >= threshold over the time window."""
    since = (datetime.utcnow() - timedelta(days=int(days))).isoformat(timespec="seconds")
    try:
        with _conn() as con:
            cur = con.execute(
                "SELECT COUNT(1), SUM(CASE WHEN confidence_score >= ? THEN 1 ELSE 0 END) FROM xp WHERE timestamp >= ?",
                (float(threshold), since),
            )
            row = cur.fetchone()
            total = int(row[0]) if row and row[0] is not None else 0
            good = int(row[1]) if row and row[1] is not None else 0
            if total <= 0:
                return 0.0
            return round(good / total, 4)
    except Exception:
        return 0.0


def verified_accuracy(days: int = 30) -> float:
    """correct / total feedback in timeframe"""
    try:
        with _conn() as con:
            since = (datetime.utcnow() - timedelta(days=int(days))).isoformat(timespec="seconds")
            rows = con.execute("SELECT verdict, COUNT(1) FROM feedback WHERE ts >= ? GROUP BY verdict", (since,)).fetchall()
            totals = {r[0]: int(r[1]) for r in rows}
            correct = int(totals.get('correct', 0))
            incorrect = int(totals.get('incorrect', 0))
            total = correct + incorrect
            return round((correct / total), 4) if total else 0.0
    except Exception:
        return 0.0


def feedback_trend(days: int = 30) -> list[dict]:
    out: list[dict] = []
    try:
        with _conn() as con:
            start = datetime.utcnow() - timedelta(days=int(days))
            for i in range(int(days)):
                d0 = (start + timedelta(days=i)).date().isoformat()
                d1 = (start + timedelta(days=i + 1)).date().isoformat()
                rows = con.execute("SELECT verdict, COUNT(1) FROM feedback WHERE ts >= ? AND ts < ? GROUP BY verdict", (d0, d1)).fetchall()
                totals = {r[0]: int(r[1]) for r in rows}
                correct = int(totals.get('correct', 0)); incorrect = int(totals.get('incorrect', 0))
                total = correct + incorrect
                acc = round((correct / total), 4) if total else 0.0
                out.append({"date": d0, "accuracy": acc, "total": total})
    except Exception:
        return out
    return out

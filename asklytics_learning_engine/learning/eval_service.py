from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from . import experience_store as xp


def _cutoff(days: int) -> str:
    return (datetime.utcnow() - timedelta(days=int(days))).isoformat(timespec="seconds")


def _within(rows: List[xp.Experience], days: int) -> List[xp.Experience]:
    t0 = _cutoff(days)
    return [e for e in rows if (e.timestamp or "") >= t0]


def size_and_growth() -> Dict[str, int]:
    rows = xp.get_all_experiences()
    total = len(rows)
    last7 = len(_within(rows, 7))
    last30 = len(_within(rows, 30))
    return {"xp_total": total, "last_7d": last7, "last_30d": last30}


def rolling_accuracy(days: int = 30) -> Dict[str, Any]:
    rows = _within(xp.get_all_experiences(), days)
    cnt = len(rows)
    correct = sum(1 for r in rows if r.success)
    latencies = [float(r.exec_ms) for r in rows if r.exec_ms is not None]
    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
    acc = (correct / cnt) if cnt else 0.0
    return {"days": days, "count": cnt, "correct": correct, "accuracy": round(acc, 4), "avg_latency_ms": round(avg_latency, 2)}


def error_buckets(days: int = 30) -> Dict[str, int]:
    rows = _within(xp.get_all_experiences(), days)
    buckets = Counter()
    for r in rows:
        et = (r.error_type or "").strip().lower()
        if not et:
            continue
        key = et if et in {"join_error","column_missing","syntax_error","timeout","empty_result"} else "other"
        buckets[key] += 1
    # ensure keys exist
    out = {k: buckets.get(k, 0) for k in ["join_error","column_missing","syntax_error","timeout","empty_result","other"]}
    return out


def by_table_join(days: int = 30) -> List[Dict[str, Any]]:
    rows = _within(xp.get_all_experiences(), days)
    stats: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(lambda: {"total":0, "issues":0, "samples": []})
    for r in rows:
        if not r.joins:
            continue
        try:
            jlist = json.loads(r.joins)
        except Exception:
            continue
        if not isinstance(jlist, list):
            continue
        for pair in jlist:
            try:
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    left, right = pair[0], pair[1]
                elif isinstance(pair, str) and "->" in pair:
                    left, right = pair.split("->", 1)
                elif isinstance(pair, str) and "," in pair:
                    left, right = pair.split(",", 1)
                else:
                    continue
                key = (left.strip(), right.strip())
                stats[key]["total"] += 1
                issue = (not r.success) or ((r.error_type or "").lower() == "join_error")
                if issue:
                    stats[key]["issues"] += 1
                    if len(stats[key]["samples"]) < 5:
                        stats[key]["samples"].append(str(r.id))
            except Exception:
                continue
    out: List[Dict[str, Any]] = []
    for (l, r), val in stats.items():
        total = max(1, int(val["total"]))
        fail_rate = round(val["issues"] / total, 4)
        out.append({"left_table": l, "right_table": r, "issues": int(val["issues"]), "fail_rate": fail_rate, "samples": val["samples"]})
    # sort by issues desc
    out.sort(key=lambda x: (-x["issues"], -x["fail_rate"]))
    return out


def top_queries(days: int = 30, k: int = 20) -> List[Dict[str, Any]]:
    rows = _within(xp.get_all_experiences(), days)
    rows.sort(key=lambda r: (float(r.score or 0.0)), reverse=True)
    out = []
    for r in rows[:k]:
        out.append({"prompt": r.user_prompt, "score": float(r.score or 0.0), "ts": r.timestamp, "provider": r.provider or ""})
    return out


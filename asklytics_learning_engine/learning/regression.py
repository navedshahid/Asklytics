from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .gemini_wrapper import GeminiWrapper
from .validator import validate_sql


DATA_DIR = Path("data/regression")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_suite(name: str) -> List[Dict[str, Any]]:
    # default empty tests; users can add to data/regression_default.json
    try:
        p = Path("asklytics_learning_engine/data/regression_default.json")
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")).get("cases", [])
    except Exception:
        pass
    return []


def _meets_expectations(sql: str, expected: Dict[str, Any]) -> Tuple[bool, str]:
    # Structural heuristics
    v = validate_sql(sql)
    if not v.ok:
        return False, "; ".join(v.errors)
    exp_cols = expected.get("columns_any") or []
    for c in exp_cols:
        if c not in sql:
            return False, f"missing column '{c}'"
    must_group = expected.get("must_group_by") or []
    if must_group:
        # naive check: all fields appear after GROUP BY
        gb = sql.lower().split("group by")
        if len(gb) < 2:
            return False, f"missing GROUP BY {','.join(must_group)}"
        tail = gb[1]
        for fld in must_group:
            if fld.lower() not in tail:
                return False, f"missing GROUP BY {fld}"
    return True, ""


def run_suite(suite_name: str = "default", tests: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    cases = tests if tests is not None else _load_suite(suite_name)
    gw = GeminiWrapper()
    results: List[Dict[str, Any]] = []
    t0 = time.time()
    for case in cases:
        cid = case.get("id") or "T"
        prompt = case.get("prompt") or ""
        expected = case.get("expected") or {}
        try:
            ctx = "-- Regression context (preview mode)"
            sql = gw.generate_sql(prompt, ctx)
            ok, reason = _meets_expectations(sql, expected)
            status = "pass" if ok else "fail"
            results.append({"id": cid, "status": status, "reason": reason, "sql": sql, "exec_ms": None})
        except Exception as e:
            results.append({"id": cid, "status": "fail", "reason": str(e), "sql": "", "exec_ms": None})
    dur = int((time.time() - t0) * 1000)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = len(results) - passed
    summary = {"passed": passed, "failed": failed, "duration_ms": dur}
    # persist dated json
    try:
        out_path = DATA_DIR / (datetime.utcnow().strftime("%Y-%m-%d") + ".json")
        out_path.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return {"summary": summary, "results": results}


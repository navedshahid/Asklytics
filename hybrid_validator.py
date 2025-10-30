"""hybrid_validator.py

Hybrid SQL validation layer combining rule-based checks with LLM repair.

This module is intentionally framework-agnostic and returns a structured
diagnostic payload that calling code can use to decide whether to execute
or repair a query. The optional Gemini-based repair path is used only
when available via `gemini_wrapper`.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import json
import re


SENSITIVE_TABLES = {"customer", "customers", "vend", "vendor", "vendors"}


@dataclass
class ValidationResult:
    is_valid: bool
    issues: List[str]
    repaired_sql: Optional[str]
    score: float

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def _has_forbidden(sql: str) -> Optional[str]:
    if re.search(r"(?i)\b(DROP|DELETE|TRUNCATE|ALTER)\b", sql):
        return "Forbidden keyword (DROP/DELETE/TRUNCATE/ALTER) detected"
    return None


def _missing_group_by_on_aggregate(sql: str) -> Optional[str]:
    if re.search(r"(?i)\bSUM\(|\bCOUNT\(|\bAVG\(|\bMIN\(|\bMAX\(", sql) and not re.search(r"(?i)\bGROUP\s+BY\b", sql):
        # Allow COUNT(*) without GROUP BY if no column references
        if not re.search(r"(?i)COUNT\(\s*\*\s*\)", sql):
            return "Aggregate functions used without GROUP BY"
    return None


def _missing_where_on_sensitive(sql: str) -> Optional[str]:
    tbls = re.findall(r"(?i)FROM\s+([\[\]\w\.]+)|JOIN\s+([\[\]\w\.]+)", sql)
    names = {t[0] or t[1] for t in tbls}
    if any(any(s in (n or "").lower() for s in SENSITIVE_TABLES) for n in names):
        if not re.search(r"(?i)\bWHERE\b", sql):
            return "Sensitive tables require a WHERE clause"
    return None


def _columns_match_schema(sql: str, schema_json: Optional[Dict[str, Any]]) -> Optional[str]:
    # Lightweight check: ensure referenced columns exist for known tables
    # schema_json expected shape: { "tables": { "schema.table": ["col1", ...] } }
    if not schema_json:
        return None
    try:
        tables = schema_json.get("tables", {})
        # naive extraction of table and column tokens
        cols = re.findall(r"(?i)SELECT\s+(.*?)\s+FROM", sql, flags=re.DOTALL)
        if not cols:
            return None
        col_segment = cols[0]
        # ignore expressions; only bare identifiers as a heuristic
        identifiers = [c.strip().strip('[]') for c in re.split(r",", col_segment)]
        known_cols = set(sum((v for v in tables.values()), []))
        missing = [c for c in identifiers if c and c != '*' and c.split() and c.split()[0] not in known_cols]
        if missing:
            return f"Columns not found in schema: {', '.join(missing[:5])}"
    except Exception:
        return None
    return None


def _repair_with_llm(sql: str) -> Optional[str]:
    """Try to repair SQL using local SQLCoder-7B as reviewer."""
    try:
        # First try local SQLCoder-7B for repair
        repaired_sql = _repair_with_sqlcoder(sql)
        if repaired_sql:
            return repaired_sql
        
        # Fallback to Gemini if available
        from gemini_wrapper import repair_sql  # type: ignore
        return repair_sql(sql)
    except Exception:
        return None

def _repair_with_sqlcoder(sql: str) -> Optional[str]:
    """Use local SQLCoder-7B to review and repair SQL."""
    try:
        # Import your existing SQLCoder setup
        import sys
        import os
        sys.path.append(os.path.dirname(__file__))
        
        # Check if SQLCoder is available
        from app import llm  # Your existing SQLCoder setup
        
        if not llm:
            return None
            
        # Create a repair prompt for SQLCoder
        repair_prompt = f"""You are an expert SQL reviewer. The following SQL has issues. Please provide a corrected version that follows T-SQL syntax.

Original SQL:
{sql}

Please provide only the corrected SQL statement, no explanations:"""

        # Use your existing LLM to generate repair
        result = llm(repair_prompt, max_tokens=512, temperature=0.1, stop=["###", "\n\n\n"], stream=False)
        repaired = result.get("choices", [{}])[0].get("text", "").strip()
        
        # Clean up the response
        repaired = repaired.replace("```sql", "").replace("```", "").strip()
        
        # Basic validation - if it looks like SQL, return it
        if repaired and repaired.upper().startswith("SELECT"):
            return repaired
            
    except Exception as e:
        print(f"SQLCoder repair failed: {e}")
        
    return None


def run(sql: str, schema_json: Optional[Dict[str, Any]] = None) -> ValidationResult:
    """Validate a SQL string, optionally repairing via LLM.

    Returns a ValidationResult with a heuristic score in [0,1].
    """
    issues: List[str] = []
    if not sql or not sql.strip():
        return ValidationResult(False, ["Empty SQL"], None, 0.0)

    checks = [
        _has_forbidden(sql),
        _missing_group_by_on_aggregate(sql),
        _missing_where_on_sensitive(sql),
        _columns_match_schema(sql, schema_json),
    ]
    for c in checks:
        if c:
            issues.append(c)

    if issues:
        repaired = _repair_with_llm(sql)
        score = 0.2 if repaired else 0.0
        return ValidationResult(False, issues, repaired, score)

    # Score can incorporate more signals later
    return ValidationResult(True, [], None, 1.0)


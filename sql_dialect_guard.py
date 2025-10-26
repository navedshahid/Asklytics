
# sql_dialect_guard.py
# ------------------------------------------------------------------
# Utilities to enforce Microsoft SQL Server (T-SQL) and auto-translate
# common PostgreSQL constructs emitted by LLMs into valid T-SQL syntax.
#
# Usage:
#   from sql_dialect_guard import enforce_tsql
#   sql = enforce_tsql(sql, dialect="tsql", mode="translate")  # or "reject"
#
# Modes:
#   - translate: convert common PG patterns to T-SQL and return the cleaned SQL
#   - reject: raise ValueError if non-T-SQL patterns are detected
#
# ------------------------------------------------------------------
import re
from typing import Literal

PG_PATTERNS = [
    r"\bLIMIT\s+\d+",
    r"\bOFFSET\s+\d+\b(?!\s*ROWS)",
    r"\bILIKE\b",
    r"::\s*[a-zA-Z0-9_]+",
    r"(?<!\w)\|\|(?!\|)",
    r"\bnow\(\)",
    r"\bCURRENT_DATE\b",
    r"\bDISTINCT\s+ON\s*\(",
    r"\bNULLS\s+(FIRST|LAST)\b",
]

def contains_postgresisms(sql: str) -> bool:
    s = sql or ""
    for p in PG_PATTERNS:
        if re.search(p, s, flags=re.IGNORECASE):
            return True
    return False

def fix_sqlserver_top(sql: str) -> str:
    """Relocate TOP to the correct position (right after SELECT[/DISTINCT])."""
    s = sql.strip()
    mt = re.search(r"\btop\s*\(?\s*(\d+)\s*\)?\b", s, flags=re.IGNORECASE)
    if mt and not re.match(r"(?i)^\s*select\s+(distinct\s+)?top", s):
        n = mt.group(1)
        s = re.sub(r"\btop\s*\(?\s*\d+\s*\)?\b", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s{2,}", " ", s)
        if re.match(r"(?i)^\s*select\s+distinct\b", s):
            s = re.sub(r"(?i)^\s*select\s+distinct\b", f"SELECT DISTINCT TOP ({n})", s, count=1)
        else:
            s = re.sub(r"(?i)^\s*select\b", f"SELECT TOP ({n})", s, count=1)
    return s

def pg_to_tsql(sql: str) -> str:
    """Translate common PostgreSQL syntax to SQL Server T-SQL."""
    s = sql.strip()

    # 1) ::casts -> CAST(expr AS type)
    s = re.sub(r"\(([^()]+)\)::([a-zA-Z0-9_\[\]]+)", r"CAST(\1 AS \2)", s)
    s = re.sub(r"(\b[a-zA-Z_][\w\.\]\[]*)::([a-zA-Z0-9_\[\]]+)", r"CAST(\1 AS \2)", s)

    # 2) ILIKE -> LIKE with LOWER(..)
    s = re.sub(r"(\b[\w\.\]\[]+\b)\s+ILIKE\s+", r"LOWER(\1) LIKE LOWER(", s, flags=re.IGNORECASE)
    s = re.sub(r"LOWER\(([^)]+)\) LIKE LOWER\(\s*([\'@:?][^)]*)\)", r"LOWER(\1) LIKE LOWER(\2)", s, flags=re.IGNORECASE)

    # 3) String concat: a || b -> CONCAT(a,b)
    while "||" in s:
        before = s
        s = re.sub(r"(\b[\w\.\]\[]+\b)\s*\|\|\s*(\b[\w\.\]\[]+\b)", r"CONCAT(\1,\2)", s)
        if s == before:
            break

    # 4) now(), current_date
    s = re.sub(r"\bnow\(\)", "GETDATE()", s, flags=re.IGNORECASE)
    s = re.sub(r"\bcurrent_date\b", "CAST(GETDATE() AS date)", s, flags=re.IGNORECASE)

    # 5) LIMIT/OFFSET
    m = re.search(r"\bLIMIT\s+(\d+)\s*(?:OFFSET\s+(\d+))?", s, flags=re.IGNORECASE)
    if m:
        n = int(m.group(1)); off = int(m.group(2) or 0)
        s = re.sub(r"\bLIMIT\s+\d+\s*(OFFSET\s+\d+)?", "", s, flags=re.IGNORECASE).rstrip()
        if re.search(r"\border\s+by\b", s, flags=re.IGNORECASE):
            s += f" OFFSET {off} ROWS FETCH NEXT {n} ROWS ONLY"
        else:
            if re.match(r"(?i)^\s*select\s+distinct\b", s):
                s = re.sub(r"(?i)^\s*select\s+distinct\b", f"SELECT DISTINCT TOP ({n})", s, count=1)
            else:
                s = re.sub(r"(?i)^\s*select\b", f"SELECT TOP ({n})", s, count=1)

    # 6) Mispositioned TOP -> correct it
    s = fix_sqlserver_top(s)

    # 7) ORDER BY ... NULLS FIRST/LAST -> emulate with CASE expressions
    def _rewrite_order_by_nulls(text: str) -> str:
        m = re.search(r"(?is)\border\s+by\s+(.+?)(?=$|offset\s+\d+\s+rows|fetch\s+next|\)|;)", text)
        if not m:
            return text
        start, end = m.span(1)
        ob_clause = text[start:end]
        # Split on commas not inside parentheses (basic)
        parts = re.split(r",(?=(?:[^()]*\([^()]*\))*[^()]*$)", ob_clause)
        new_parts = []
        changed = False
        for p in parts:
            f = p.strip()
            nm = re.match(r"(?is)^(.*?)(?:\s+(ASC|DESC))?\s+NULLS\s+(FIRST|LAST)\s*$", f)
            if nm:
                base = nm.group(1).strip()
                direction = nm.group(2) or ""
                nulls = (nm.group(3) or "").upper()
                if nulls == "LAST":
                    # Nulls last: sort nulls after non-nulls
                    case = f"CASE WHEN {base} IS NULL THEN 1 ELSE 0 END"
                else:
                    # Nulls first
                    case = f"CASE WHEN {base} IS NULL THEN 0 ELSE 1 END"
                dir_sql = f" {direction}" if direction else ""
                new_parts.append(f"{case}, {base}{dir_sql}")
                changed = True
            else:
                # Drop stray 'NULLS FIRST/LAST' if present to avoid syntax error
                f2 = re.sub(r"(?is)\s+NULLS\s+(FIRST|LAST)\s*$", "", f)
                if f2 != f:
                    changed = True
                new_parts.append(f2)
        if not changed:
            return text
        new_ob = ", ".join(new_parts)
        return text[:start] + new_ob + text[end:]

    s = _rewrite_order_by_nulls(s)
    return s.strip()

def enforce_tsql(sql: str, dialect: str = "tsql", mode: Literal["translate","reject"]="translate") -> str:
    """
    Ensure SQL is valid T-SQL if dialect == 'tsql'.
    - translate: attempt to convert common Postgresisms into T-SQL, return cleaned SQL
    - reject: raise ValueError if any non-T-SQL pattern is detected
    """
    if not sql:
        return sql
    if dialect != "tsql":
        return sql.strip()

    s = sql.strip()
    if mode == "reject":
        if contains_postgresisms(s):
            raise ValueError("Non-T-SQL syntax detected (e.g., LIMIT/ILIKE/::). Regenerate strictly valid T-SQL.")
        return fix_sqlserver_top(s)

    if contains_postgresisms(s):
        s = pg_to_tsql(s)
    s = fix_sqlserver_top(s)
    return s.strip()

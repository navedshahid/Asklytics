import re
import sqlglot
from sqlglot import transpile, exp
import logging

logger = logging.getLogger("AskLytics-SQL")


def _sanitize_non_tsql(sql: str) -> str:
    """Replace MySQL-style backticks/quoted idents with T-SQL brackets."""
    if "`" in sql:
        sql = re.sub(r"`([^`]+)`", r"[\1]", sql)
    # Convert double-quoted identifiers to brackets (keeps string literals intact heuristically)
    sql = re.sub(r'"([A-Za-z_][\w\.]*)"', r"[\1]", sql)
    return sql


def transpile_to_tsql(sql: str, read_dialect: str = "tsql") -> str:
    """Robust SQL transpilation using sqlglot with sane fallbacks and sanitization."""
    original_sql = sql
    try:
        transpiled = transpile(sql, read=read_dialect, write="tsql", pretty=True)
        if transpiled:
            return transpiled[0]
    except Exception as e:
        logger.warning(f"SQL Transpilation failed (read={read_dialect}): {e}. Trying sanitization.")

    # Try sanitizing non-T-SQL quoting/backticks then re-run transpile using mysql reader as a tolerant parse
    sanitized = _sanitize_non_tsql(original_sql)
    if sanitized != original_sql:
        logger.info("Sanitized non-T-SQL quoting/backticks before transpile.")
    try:
        transpiled = transpile(sanitized, read="mysql", write="tsql", pretty=True)
        if transpiled:
            return transpiled[0]
    except Exception as e:
        logger.warning(f"SQL Transpilation failed after sanitization: {e}. Using sanitized SQL.")

    return sanitized


def validate_tsql(sql: str) -> bool:
    """Basic validation using sqlglot expression tree."""
    try:
        sqlglot.parse_one(sql, read="tsql")
        return True
    except Exception as e:
        logger.warning(f"SQL Validation failed: {e}")
        return False


def inject_safety_top(sql: str, limit: int = 1000) -> str:
    """Inject SELECT TOP (N) if not present using sqlglot for safety."""
    try:
        expression = sqlglot.parse_one(sql, read="tsql")

        # If it's a SELECT, check if TOP/LIMIT is there
        if isinstance(expression, exp.Select):
            if not expression.args.get("limit") and not expression.args.get("top"):
                expression = expression.top(limit)
                return expression.sql(dialect="tsql")

        return sql
    except Exception:
        # Fallback to simple regex if sqlglot fails to parse
        if not re.search(r'(?i)\bTOP\s*\(?\s*\d+', sql):
            return re.sub(r'(?i)^(\s*SELECT\s+(?:DISTINCT\s+)?)', r'\1TOP ({}) '.format(limit), sql)
        return sql

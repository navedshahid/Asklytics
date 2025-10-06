
"""
SQL safety validator (lightweight).
- Rejects any DDL/DML
- Enforces SELECT-only
- Injects TOP cap if missing (patcher)
- Provides structured reasons on failure

This is a heuristic layer; for production, consider parsing with an AST library
or T-SQL grammar to be more robust.
"""
import re

class ValidationError(Exception):
    def __init__(self, reasons: list[str]):
        super().__init__("\n".join(reasons))
        self.reasons = reasons

class SQLValidator:
    def __init__(self, default_top=500):
        self.default_top = default_top

    def policies_block(self) -> str:
        return (
            "1) SELECT-only. 2) No UPDATE/DELETE/INSERT/ALTER/DROP/CREATE/TRUNCATE. "
            f"3) Always include TOP {self.default_top} unless user asks otherwise. 4) No CROSS JOIN without filters."
        )

    def assert_safe(self, sql: str):
        s = sql.strip().lower()
        reasons = []
        if not s.startswith("select"):
            reasons.append("Query must start with SELECT.")
        banned = [" update ", " delete ", " insert ", " alter ", " drop ", " truncate ", " merge ", " exec ", " execute "]
        for b in banned:
            if b in f" {s} ":
                reasons.append(f"Found banned token: {b.strip()}")
        if "cross join" in s and " on " not in s:
            reasons.append("CROSS JOIN without ON clause is not allowed.")
        if reasons:
            raise ValidationError(reasons)

    def patch_sql(self, sql: str) -> str:
        """
        Adds TOP cap if missing in the first SELECT clause.
        """
        # Inject TOP after SELECT if not present, naive but effective for MVP
        m = re.match(r"(?is)\s*select\s+(distinct\s+)?", sql)
        if not m:
            return sql
        head = sql[m.end():]
        if re.match(r"(?is)\s*top\s+\d+", head):
            return sql
        return sql[:m.end()] + f"TOP {self.default_top} " + sql[m.end():]

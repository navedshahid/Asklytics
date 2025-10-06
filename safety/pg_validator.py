import re
class ValidationError(Exception):
    def __init__(self, reasons): self.reasons = reasons; super().__init__("\n".join(reasons))

class PGValidator:
    def __init__(self, default_limit=500): self.default_limit=default_limit
    def policies_block(self): 
        return f"1) SELECT-only. 2) No UPDATE/DELETE/INSERT/ALTER/DROP/TRUNCATE/MERGE; 3) Always include LIMIT {self.default_limit} unless specified; 4) No CROSS JOIN without filters."
    def assert_safe(self, sql: str):
        s=sql.strip().lower(); reasons=[]
        if not s.startswith("select"): reasons.append("Query must start with SELECT.")
        for b in [" update "," delete "," insert "," alter "," drop "," truncate "," merge "," call "," do "]:
            if b in f" {s} ": reasons.append(f"Banned token: {b.strip()}")
        if "cross join" in s and " on " not in s: reasons.append("CROSS JOIN without ON is not allowed.")
        if reasons: raise ValidationError(reasons)
    def patch_sql(self, sql: str) -> str:
        if re.search(r"(?is)\blimit\s+\d+\b", sql): return sql
        return sql.rstrip().rstrip(";") + f" LIMIT {self.default_limit};"

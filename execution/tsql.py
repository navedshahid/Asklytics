# execution/tsql.py
import os, time, pyodbc, pandas as pd

class SafeTSQLExecutor:
    def __init__(self, dsn_env_var="QP_SQL_DSN", timeout_sec=30, row_cap=5000, audit_path="./storage/audit.sqlite"):
        self.dsn_env_var = dsn_env_var
        self.timeout_sec = timeout_sec
        self.row_cap = row_cap
        self.audit_path = audit_path

    def _cap_sql(self, sql: str) -> str:
        s = sql.strip().rstrip(";")
        # enforce a hard cap if caller forgot TOP
        if s.lower().startswith("select") and " top " not in s.lower():
            # naive injection of TOP… for complex queries you may want AST patching
            return "SET ROWCOUNT {cap}; {q}; SET ROWCOUNT 0;".format(cap=self.row_cap, q=s + ";")
        return s + ";"

    def execute(self, sql: str, dsn_override: str | None = None):
        t0 = time.time()
        dsn = dsn_override or os.environ.get(self.dsn_env_var)
        if not dsn:
            raise RuntimeError(f"Set {self.dsn_env_var}")

        cap_sql = self._cap_sql(sql)

        with pyodbc.connect(dsn, timeout=self.timeout_sec) as cn:
            cur = cn.cursor()
            # Keep it snappy & safe for analytics
            cur.execute(f"SET LOCK_TIMEOUT {self.timeout_sec*1000};")
            cur.execute("SET NOCOUNT ON;")
            cur.execute(cap_sql)

            # If the statement returns rows:
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = []
            if cols:
                # fetch up to row_cap rows
                fetched = cur.fetchmany(self.row_cap)
                while fetched:
                    rows.extend(fetched)
                    if len(rows) >= self.row_cap:
                        break
                    fetched = cur.fetchmany(self.row_cap - len(rows))

            df = pd.DataFrame.from_records(rows, columns=cols) if cols else pd.DataFrame()

        meta = {
            "elapsed_ms": int((time.time() - t0) * 1000),
            "rowcount": len(df),
        }
        return df, meta

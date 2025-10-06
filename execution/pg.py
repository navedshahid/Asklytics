import psycopg2, pandas as pd, os, time

class SafePGExecutor:
    def __init__(self, dsn_env="QP_PG_DSN", timeout_sec=30, row_cap=5000):
        self.dsn_env=dsn_env; self.timeout_sec=timeout_sec; self.row_cap=row_cap
    def execute(self, sql: str):
        t0=time.time()
        dsn=os.environ.get(self.dsn_env)
        if not dsn: raise RuntimeError(f"Set {self.dsn_env}")
        with psycopg2.connect(dsn) as cn:
            with cn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {self.timeout_sec*1000}")
            # enforce cap by wrapping
            capped = f"{sql.rstrip(';')} LIMIT {self.row_cap};"
            df = pd.read_sql(capped, cn)
        return df, {"elapsed_ms":int((time.time()-t0)*1000),"rowcount":len(df)}

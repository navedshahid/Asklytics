
"""
SQLite-backed audit logger for questions and executed SQL.
"""
import sqlite3, time, os
from pathlib import Path

class AuditLogger:
    def __init__(self, db_path="./storage/audit.sqlite"):
        self.db = db_path
        Path(os.path.dirname(db_path)).mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self):
        with sqlite3.connect(self.db) as con:
            con.execute("""
            CREATE TABLE IF NOT EXISTS audit(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, user_id TEXT, question TEXT, sql TEXT, success INT, rows INT, reasons TEXT
            )""")
            con.commit()

    def log(self, user_id: str, question: str, sql: str, success: bool, rows: int = 0, reasons: list[str] | None = None):
        with sqlite3.connect(self.db) as con:
            con.execute("INSERT INTO audit (ts,user_id,question,sql,success,rows,reasons) VALUES (?,?,?,?,?,?,?)",
                        (time.time(), user_id, question, sql, 1 if success else 0, rows, None if not reasons else "; ".join(reasons)))
            con.commit()

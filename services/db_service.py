import pyodbc
from contextlib import contextmanager
from threading import Lock
from typing import Optional, List, Dict, Any, Generator
import time
import logging
from services.config_service import get_settings

logger = logging.getLogger("AskLytics-DB")

class ConnectionPool:
    """A thread-safe connection pool for pyodbc."""
    
    def __init__(self, dsn: str, size: int = 5):
        self.dsn = dsn
        self.size = size
        self._pool = []
        self._lock = Lock()
        self._initialize_pool()

    def _initialize_pool(self):
        with self._lock:
            for _ in range(self.size):
                try:
                    conn = pyodbc.connect(self.dsn, timeout=10)
                    self._pool.append(conn)
                except Exception as e:
                    logger.error(f"Failed to create pooled connection: {e}")

    def get_connection(self) -> pyodbc.Connection:
        with self._lock:
            if self._pool:
                return self._pool.pop()
        # Fallback to ad-hoc connection if pool is empty
        logger.warning("Connection pool empty, creating ad-hoc connection")
        return pyodbc.connect(self.dsn, timeout=10)

    def return_connection(self, conn: pyodbc.Connection):
        with self._lock:
            if len(self._pool) < self.size:
                self._pool.append(conn)
            else:
                try:
                    conn.close()
                except Exception:
                    pass

_pool: Optional[ConnectionPool] = None
_pool_lock = Lock()

@contextmanager
def get_db_connection() -> Generator[pyodbc.Connection, None, None]:
    """Context managed DB connection from the global pool."""
    global _pool
    settings = get_settings()
    db_cfg = settings.db
    
    if not db_cfg.configured:
        raise ConnectionError("Database not configured")

    # Construct DSN with security settings
    dsn_parts = [
        f"DRIVER={{{db_cfg.driver}}}",
        f"SERVER={db_cfg.server}",
        f"DATABASE={db_cfg.database}",
        f"UID={db_cfg.uid}",
        f"PWD={db_cfg.pwd}",
        f"Encrypt={'yes' if db_cfg.encrypt else 'no'}",
        f"TrustServerCertificate={'yes' if db_cfg.trust_server_certificate else 'no'}"
    ]
    dsn = ";".join(dsn_parts)

    with _pool_lock:
        if not _pool or _pool.dsn != dsn:
            if _pool:
                logger.info("DSN changed, re-initializing connection pool")
            _pool = ConnectionPool(dsn)

    conn = _pool.get_connection()
    try:
        yield conn
    finally:
        _pool.return_connection(conn)

def safe_execute_sql(cursor, sql: str, timeout_seconds: int = 30) -> tuple[List[str], List[Dict[str, Any]], float]:
    """Execute SQL safely and return results with timing."""
    # Note: Modern pyodbc supports timeout in execute if the driver supports it
    t0 = time.time()
    try:
        cursor.execute(sql)
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows = []
        # Support both SELECT and non-SELECT
        if cursor.description:
            rows = [dict(zip(columns, r)) for r in cursor.fetchall()]
        exec_ms = (time.time() - t0) * 1000.0
        return columns, rows, exec_ms
    except Exception as e:
        logger.error(f"SQL Execution Error: {e}")
        raise

"""dao.py

Minimal data access layer (DAO) to abstract storage used by auxiliary
components such as audit and metrics. Defaults to SQLite and can be
expanded to PostgreSQL by switching the engine key.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


EngineName = Literal["sqlite", "postgres"]


@dataclass
class EngineConfig:
    engine: EngineName = "sqlite"
    dsn: str | None = None


def resolve_engine_from_env(default_root: Path) -> EngineConfig:
    """Create a simple engine config from environment variables.

    Supported env vars:
      - DB_ENGINE: sqlite|postgres
      - DB_DSN: connection string for postgres
    """
    import os

    eng = (os.getenv("DB_ENGINE") or "sqlite").strip().lower()
    if eng not in ("sqlite", "postgres"):
        eng = "sqlite"
    dsn = os.getenv("DB_DSN")
    if eng == "sqlite" and not dsn:
        dsn = str((default_root / "data" / "app.db").resolve())
    return EngineConfig(engine=eng, dsn=dsn)


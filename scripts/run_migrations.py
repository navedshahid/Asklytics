"""Apply SQL migrations from the ./migrations directory.

Usage:
    python scripts/run_migrations.py [--database <sqlite path or sqlite:/// URL>]

Defaults to the learning store database (LEARN_DB_URL env or ./learning_store.db).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations"


def resolve_sqlite_path(value: str | None) -> Path:
    url = (value or os.getenv("LEARN_DB_URL") or "sqlite:///./learning_store.db").strip()
    if url.startswith("sqlite:///"):
        path_str = url.replace("sqlite:///", "", 1)
    else:
        path_str = url
    return (ROOT / path_str).resolve() if not Path(path_str).is_absolute() else Path(path_str).resolve()


def apply_migration(conn: sqlite3.Connection, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    if not sql.strip():
        return
    conn.executescript(sql)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply AskLytics SQL migrations")
    parser.add_argument(
        "--database",
        "-d",
        help="SQLite database path or sqlite:/// URL (default: LEARN_DB_URL or ./learning_store.db)",
    )
    args = parser.parse_args()

    db_path = resolve_sqlite_path(args.database)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migrations:
        print("No migrations found.")
        return 0

    print(f"Applying {len(migrations)} migration(s) to {db_path}")
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        for mig in migrations:
            print(f"- {mig.name}")
            try:
                apply_migration(conn, mig)
            except Exception as exc:
                conn.rollback()
                print(f"  ! Failed: {exc}", file=sys.stderr)
                return 1
        conn.commit()
    finally:
        conn.close()
    print("All migrations applied successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

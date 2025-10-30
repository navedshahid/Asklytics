"""Seed demo users and roles for local development.

The script populates a lightweight `demo_users` table inside metadata.db so
UI components can list sample users/roles.

Usage:
    python scripts/seed_fake_users.py [--database <sqlite path or sqlite:/// URL>]
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_USERS = [
    {
        "user_id": "analyst.alice",
        "display_name": "Alice Analyst",
        "email": "alice@example.com",
        "roles": "analyst",
    },
    {
        "user_id": "auditor.arnav",
        "display_name": "Arnav Auditor",
        "email": "arnav@example.com",
        "roles": "auditor,pii_viewer",
    },
    {
        "user_id": "exec.emma",
        "display_name": "Emma Executive",
        "email": "emma@example.com",
        "roles": "executive",
    },
]


def resolve_metadata_path(value: str | None) -> Path:
    url = (value or os.getenv("META_DB_URL") or "sqlite:///./metadata.db").strip()
    if url.startswith("sqlite:///"):
        path_str = url.replace("sqlite:///", "", 1)
    else:
        path_str = url
    path = Path(path_str)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def seed_users(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS demo_users (
            user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            email TEXT,
            roles TEXT NOT NULL
        )
        """
    )
    for user in SAMPLE_USERS:
        conn.execute(
            "INSERT OR REPLACE INTO demo_users (user_id, display_name, email, roles) VALUES (?,?,?,?)",
            (user["user_id"], user["display_name"], user["email"], user["roles"]),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo users/roles into metadata.db")
    parser.add_argument(
        "--database",
        "-d",
        help="SQLite database path or sqlite:/// URL (default: META_DB_URL or ./metadata.db)",
    )
    args = parser.parse_args()

    db_path = resolve_metadata_path(args.database)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        seed_users(conn)
        conn.commit()
    finally:
        conn.close()

    print(f"Seeded {len(SAMPLE_USERS)} demo users into {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

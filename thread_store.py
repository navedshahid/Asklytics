"""thread_store.py

Simple JSON file backed thread store for chat history.
Safe for single-process development usage.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any
import json
import time
import uuid


@dataclass
class Message:
    type: str
    content: str


@dataclass
class Thread:
    id: str
    title: str
    messages: List[Message]
    updated_at: float


class ThreadStore:
    def __init__(self, root: Path):
        self.path = root / "data" / "threads.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write(self, rows: List[Dict[str, Any]]):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)

    def list(self, user_id: str | None = None, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self._read()
        if user_id:
            rows = [r for r in rows if r.get("user_id") == user_id]
        rows = sorted(rows, key=lambda r: r.get("updated_at", 0), reverse=True)
        return [{"id": r["id"], "title": r.get("title", "Chat"), "updated_at": r.get("updated_at", 0)} for r in rows[:limit]]

    def create(self, user_id: str, title: str = "New Chat") -> Dict[str, Any]:
        rows = self._read()
        tid = uuid.uuid4().hex
        row = {"id": tid, "user_id": user_id, "title": title or "New Chat", "messages": [], "updated_at": time.time()}
        rows.append(row)
        self._write(rows)
        return {"id": tid, "title": row["title"]}

    def get(self, tid: str) -> Dict[str, Any] | None:
        for r in self._read():
            if r.get("id") == tid:
                return r
        return None

    def rename(self, tid: str, title: str) -> bool:
        rows = self._read()
        ok = False
        for r in rows:
            if r.get("id") == tid:
                r["title"] = title
                r["updated_at"] = time.time()
                ok = True
                break
        if ok:
            self._write(rows)
        return ok

    def delete(self, tid: str) -> bool:
        rows = self._read()
        n = len(rows)
        rows = [r for r in rows if r.get("id") != tid]
        if len(rows) != n:
            self._write(rows)
            return True
        return False

    def add_message(self, tid: str, msg_type: str, content: str) -> bool:
        rows = self._read()
        ok = False
        for r in rows:
            if r.get("id") == tid:
                r.setdefault("messages", []).append({"type": msg_type, "content": content})
                r["updated_at"] = time.time()
                ok = True
                break
        if ok:
            self._write(rows)
        return ok

    def set_state(self, tid: str, state: Dict[str, Any]) -> bool:
        rows = self._read()
        ok = False
        for r in rows:
            if r.get("id") == tid:
                r["state"] = state
                r["updated_at"] = time.time()
                ok = True
                break
        if ok:
            self._write(rows)
        return ok

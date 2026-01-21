"""
Training Engine

Captures user question, plan, SQL, and feedback into a JSONL dataset.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any
from threading import Lock


class TrainingEngine:
    def __init__(self, path: str = "data/training_dataset.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def log_example(self, record: Dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

import numpy as np

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None  # type: ignore

from .embedder import embed_text
from .feedback_dao import mark_retrain_used


LEARN_DB_URL = os.getenv("LEARN_DB_URL", "sqlite:///./learning_store.db")
DB_PATH = LEARN_DB_URL.split("sqlite:///")[-1] if LEARN_DB_URL.startswith("sqlite") else "./learning_store.db"

DATA_DIR = os.path.join("asklytics_learning_engine", "data")
INDEX_PATH = os.path.join(DATA_DIR, "faiss_index.faiss")
META_PATH = os.path.join(DATA_DIR, "meta.json")


def _load_index():
    if faiss is None:
        return None, None
    if not (os.path.exists(INDEX_PATH) and os.path.exists(META_PATH)):
        return None, None
    index = faiss.read_index(INDEX_PATH)
    with open(META_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return index, meta


def _save_index(index, meta):
    os.makedirs(DATA_DIR, exist_ok=True)
    faiss.write_index(index, INDEX_PATH)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f)


def _get_xp_prompt(xp_id: int) -> Optional[str]:
    con = sqlite3.connect(DB_PATH)
    try:
        row = con.execute("SELECT user_prompt FROM xp WHERE id=?", (int(xp_id),)).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def add_example(xp_id: int, *, feedback_id: Optional[int] = None) -> None:
    """Embed the xp.user_prompt and upsert into FAISS index with the id.

    Notes:
    - Uses normalized cosine (IP index + normalize L2)
    - Simple upsert: remove prior id if present, then add
    - Marks feedback.retrain_used=1 when feedback_id provided
    """
    if faiss is None:
        return
    text = _get_xp_prompt(int(xp_id))
    if not text:
        return
    vec = embed_text(text).astype("float32").reshape(1, -1)
    faiss.normalize_L2(vec)
    index, meta = _load_index()
    dim = vec.shape[1]
    if index is None:
        # create a fresh index
        index = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))
        meta = {"ids": [], "dim": dim}
    # If dimension changed, rebuild from scratch with just this vector
    if int(meta.get("dim") or 0) != int(dim):
        index = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))
        meta = {"ids": [], "dim": dim}
    # Remove prior id if it exists
    try:
        if meta.get("ids") and int(xp_id) in set(meta["ids"]):
            index.remove_ids(np.asarray([int(xp_id)], dtype="int64"))
            meta["ids"] = [i for i in meta["ids"] if int(i) != int(xp_id)]
    except Exception:
        pass
    index.add_with_ids(vec, np.asarray([int(xp_id)], dtype="int64"))
    meta["ids"].append(int(xp_id))
    _save_index(index, meta)
    if feedback_id is not None:
        try:
            mark_retrain_used(int(feedback_id))
        except Exception:
            pass


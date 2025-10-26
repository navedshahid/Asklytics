from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None  # type: ignore

DATA_DIR = Path("asklytics_learning_engine/data")
INDEX_PATH = DATA_DIR / "faiss_index.faiss"
META_PATH = DATA_DIR / "meta.json"


@dataclass
class FaissIndexMeta:
    ids: List[int]
    dim: int


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_sentence_transformer():
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        model_name = os.getenv("LEARN_EMBED_MODEL", "all-MiniLM-L6-v2")
        return SentenceTransformer(model_name)
    except Exception:
        return None


def embed_text(text: str) -> np.ndarray:
    """Embed a single text using local SentenceTransformer or fallback to Gemini embeddings.

    Returns a 1D numpy array of floats.
    """
    st = _load_sentence_transformer()
    if st is not None:
        vec = st.encode([text])[0]
        return np.asarray(vec, dtype="float32")

    # Fallback: Gemini embeddings (requires network + API key)
    try:
        import google.generativeai as genai  # type: ignore

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY missing for embedding fallback")
        genai.configure(api_key=api_key)
        model = os.getenv("LEARN_EMBEDDING_MODEL", "models/embedding-001")
        resp = genai.embed_content(model=model, content=text)
        vec = resp["embedding"] if isinstance(resp, dict) else resp.embedding
        return np.asarray(vec, dtype="float32")
    except Exception as e:
        raise RuntimeError(f"No embedding backend available: {e}")


def build_faiss_index(pairs: List[Tuple[int, str]]) -> None:
    """Build a FAISS index from (xp_id, text) pairs and persist artifacts.

    - Stores index at data/faiss_index.faiss
    - Stores metadata (id ordering, dim) at data/meta.json
    """
    _ensure_dirs()
    if faiss is None:
        raise RuntimeError("faiss not installed; cannot build index")

    embeds: List[np.ndarray] = []
    ids: List[int] = []
    for xp_id, text in pairs:
        vec = embed_text(text)
        ids.append(xp_id)
        embeds.append(vec)
    if not embeds:
        # create empty artifacts
        with open(META_PATH, "w", encoding="utf-8") as f:
            json.dump({"ids": [], "dim": 0}, f)
        if INDEX_PATH.exists():
            INDEX_PATH.unlink()
        return

    X = np.vstack(embeds).astype("float32")
    dim = X.shape[1]
    index = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))
    # Normalize for IP == cosine
    faiss.normalize_L2(X)
    index.add_with_ids(X, np.asarray(ids, dtype="int64"))
    faiss.write_index(index, str(INDEX_PATH))
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump({"ids": ids, "dim": dim}, f)


def _load_index():
    if faiss is None:
        return None, None
    if not INDEX_PATH.exists() or not META_PATH.exists():
        return None, None
    index = faiss.read_index(str(INDEX_PATH))
    with open(META_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return index, meta


def query_faiss(prompt_embedding: np.ndarray, k: int = 3) -> List[int]:
    """Return top-k xp ids by cosine similarity from FAISS (if available)."""
    index, meta = _load_index()
    if index is None or meta is None:
        return []
    vec = prompt_embedding.astype("float32").reshape(1, -1)
    faiss.normalize_L2(vec)
    D, I = index.search(vec, k)
    ids = [int(i) for i in I[0] if i != -1]
    return ids


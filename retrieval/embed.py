# retrieval/embed.py
import os
import numpy as np
from pathlib import Path

import faiss

# Switch to sentence-transformers; fall back to hash if not available
_MODEL = None
_DEVICE = "cpu"

def _ensure_model():
    global _MODEL, _DEVICE
    if _MODEL is not None:
        return
    try:
        import torch
        from sentence_transformers import SentenceTransformer
        _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        name = os.environ.get("QP_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        _MODEL = SentenceTransformer(name, device=_DEVICE)
        print(f"[embed] Using {name} on {_DEVICE}")
    except Exception as ex:
        print("[embed] Fallback to cheap hash embeddings:", ex)
        _MODEL = None
        _DEVICE = "cpu"

# --- replace _hash_vec with this safe version ---
def _hash_vec(text: str, dim: int = 384) -> np.ndarray:
    """
    Generate a deterministic pseudo-embedding of arbitrary dimension.
    Uses 64-byte blake2b chunks and repeats/concats to reach `dim`.
    """
    import hashlib
    # base 64-byte digest
    h = hashlib.blake2b(text.encode("utf-8"), digest_size=64).digest()
    x = bytearray()
    cnt = 0
    # repeat with a salt so each chunk differs
    while len(x) < dim:
        salt = cnt.to_bytes(2, "little")
        digest = hashlib.blake2b(h + salt, digest_size=64).digest()
        x.extend(digest)
        cnt += 1
    arr = np.frombuffer(bytes(x[:dim]), dtype=np.uint8).astype(np.float32)
    n = np.linalg.norm(arr) + 1e-9
    return arr / n

def normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True) + 1e-9
    return x / n

def embed_texts(texts: list[str], dim: int = 384) -> np.ndarray:
    _ensure_model()
    if _MODEL is None:
        return normalize(np.stack([_hash_vec(t, dim) for t in texts], axis=0))
    vecs = _MODEL.encode(texts, batch_size=int(os.environ.get("QP_EMBED_BS","64")), show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True)
    return vecs.astype(np.float32)

def save_faiss(path: Path, vecs: np.ndarray):
    index = faiss.IndexFlatIP(vecs.shape[1])  # cosine sim with normalized vectors
    index.add(vecs.astype(np.float32))
    faiss.write_index(index, str(path))

def load_faiss(path: Path):
    return faiss.read_index(str(path))


"""
Embedding utilities. For portability we use a tiny hashing-based embedding fallback to avoid
heavy model downloads in air-gapped setups. In production, replace with SentenceTransformer
and persist FAISS index the same way.
"""
import numpy as np
import faiss
import json
from pathlib import Path
from hashlib import blake2b

def cheap_hash_vec(text: str, dim: int = 384) -> np.ndarray:
    """
    Very lightweight, deterministic hash embedding (placeholder).
    Replace with SentenceTransformer in production for better semantic quality.
    """
    h = blake2b(text.encode("utf-8"), digest_size=dim//8).digest()
    v = np.frombuffer(h, dtype=np.uint8).astype(np.float32)
    # If dim not multiple of len(v), tile
    v = np.resize(v, dim).astype(np.float32)
    return v

def normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True) + 1e-9
    return x / n

def embed_texts(texts: list[str], dim: int = 384) -> np.ndarray:
    vecs = np.stack([cheap_hash_vec(t, dim) for t in texts], axis=0)
    return normalize(vecs)

def save_faiss(path: Path, vecs: np.ndarray):
    index = faiss.IndexFlatIP(vecs.shape[1])  # cosine via normalized IP
    index.add(vecs.astype(np.float32))
    faiss.write_index(index, str(path))

def load_faiss(path: Path):
    return faiss.read_index(str(path))


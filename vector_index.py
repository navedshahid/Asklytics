"""vector_index.py

Abstraction over vector index backends. Currently supports wrapping the
existing FAISS index used by AskLytics while defining an interface that
can be extended to pgvector or Milvus.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Tuple, Optional


@dataclass
class QueryResult:
    idx: int
    score: float


class VectorIndex:
    """Interchangeable vector index with pluggable backends.

    When backend == "faiss", an existing faiss.Index can be injected.
    """

    def __init__(self, backend: str = "faiss", handle: Optional[Any] = None):
        self.backend = backend
        self.handle = handle

    def is_ready(self) -> bool:
        if self.backend == "faiss":
            try:
                return getattr(self.handle, "ntotal", 0) > 0
            except Exception:
                return False
        # Future backends can perform their own readiness checks
        return False

    def size(self) -> int:
        if self.backend == "faiss":
            try:
                return int(getattr(self.handle, "ntotal", 0))
            except Exception:
                return 0
        return 0

    def search(self, vectors, k: int = 7) -> Tuple[List[List[float]], List[List[int]]]:
        """Search raw vectors against the backend.

        Returns (distances, indices) to match FAISS semantics.
        """
        if self.backend == "faiss":
            assert self.handle is not None, "FAISS handle missing"
            return self.handle.search(vectors, k)
        raise NotImplementedError("VectorIndex backend not implemented: %s" % self.backend)



"""
HybridSelector: combines vector search (FAISS) with lexical BM25-ish scoring
and expands along FK relationships to propose a compact working set of tables/columns.
"""
from pathlib import Path
import json
import numpy as np
from rapidfuzz import fuzz
from .embed import load_faiss
from catalog.loader import CatalogLoader

class HybridSelector:
    
    def __init__(self, base_dir="./catalog/artifacts"):
        self.base = Path(base_dir)
        self.catalog = CatalogLoader(base_dir=base_dir)
        self.index = load_faiss(self.base/"columns.faiss") if (self.base/"columns.faiss").exists() else None

    def _vector_hits(self, question: str, topk: int = 64):
        if not self.index:
            return []  # No vectors yet
        # We reuse the cheap hash embedding logic implicitly via FAISS index already stored.
        # For simplicity, we cannot query without the original embedding model; this is a placeholder.
        # In prod, maintain a shared embedder for both index build and query.
        from .embed import embed_texts
        qv = embed_texts([question])
        D, I = self.index.search(qv.astype(np.float32), topk)
        return list(I[0])

    def _lexical_hits(self, question: str, limit: int = 64):
        # Crude lexical similarity over "table.column name dtype"
        cols = self.catalog.list_columns()
        scores = []
        for i, c in enumerate(cols):
            name = f"{c['table']}.{c['name']} {c.get('dtype','')}"
            s = fuzz.token_set_ratio(question, name)
            if s > 20:
                scores.append((i, s))
        scores.sort(key=lambda x: x[1], reverse=True)
        return [i for i,_ in scores[:limit]]

    def select(self, question: str, k_tables: int = 6, k_columns: int = 24, allow_tables: set[str] | None = None):
        cols = self.catalog.list_columns()
        vec_idxs = set(self._vector_hits(question, topk=64)) if self.index else set()
        lex_idxs = set(self._lexical_hits(question, limit=64))
        merged = list(vec_idxs.union(lex_idxs))

        table_scores = {}
        for idx in merged:
            if 0 <= idx < len(cols):
                t = cols[idx]["table"]
                if allow_tables and t not in allow_tables:
                    continue
                table_scores[t] = table_scores.get(t, 0) + 1

        # expand one-hop via relationships
        rels = self.catalog.list_relationships()
        neighbors = {}
        for r in rels:
            neighbors.setdefault(r["from"], set()).add(r["to"])
            neighbors.setdefault(r["to"], set()).add(r["from"])

        top_tables = [t for t,_ in sorted(table_scores.items(), key=lambda x: x[1], reverse=True)]
        exp = set()
        for t in top_tables:
            if allow_tables and t not in allow_tables: continue
            exp.add(t)
            for nb in neighbors.get(t, set()):
                if not allow_tables or nb in allow_tables:
                    exp.add(nb)

        final_tables = list(exp)[:k_tables]
        final_cols = [c for c in cols if c["table"] in final_tables][:k_columns]
        final_rels = [r for r in rels if r["from"] in final_tables and r["to"] in final_tables]

        return {"tables": final_tables, "columns": final_cols, "relationships": final_rels}


    def explain(self, retrieval: dict) -> str:
        t = ", ".join(retrieval.get("tables", []))
    def select(self, question: str, k_tables: int = 6, k_columns: int = 24, allow_tables: set[str] | None = None):
        cols = self.catalog.list_columns()
        vec_idxs = set(self._vector_hits(question, topk=64)) if self.index else set()
        lex_idxs = set(self._lexical_hits(question, limit=64))
        merged = list(vec_idxs.union(lex_idxs))

        # Map to tables and score
        table_scores = {}
        for idx in merged:
            if 0 <= idx < len(cols):
                t = cols[idx]["table"]
                # If a filter exists, ignore cols from disallowed tables up front
                if allow_tables and t not in allow_tables:
                    continue
                table_scores[t] = table_scores.get(t, 0) + 1

        # Relationship expansion
        rels = self.catalog.list_relationships()
        neighbors = {}
        for r in rels:
            neighbors.setdefault(r["from"], set()).add(r["to"])
            neighbors.setdefault(r["to"], set()).add(r["from"])

        top_tables = [t for t,_ in sorted(table_scores.items(), key=lambda x: x[1], reverse=True)]

        # Expand one hop, but keep within allowlist if provided
        exp_tables = set()
        for t in top_tables:
            if allow_tables and t not in allow_tables:
                continue
            exp_tables.add(t)
            for nb in neighbors.get(t, set()):
                if (not allow_tables) or (nb in allow_tables):
                    exp_tables.add(nb)

        # Final tables trimmed
        final_tables = list(exp_tables)[:k_tables]

        # Columns & relationships filtered consistently
        final_cols = [c for c in cols if c["table"] in final_tables][:k_columns]
        final_rels = [r for r in rels if r["from"] in final_tables and r["to"] in final_tables]

        return {"tables": final_tables, "columns": final_cols, "relationships": final_rels}
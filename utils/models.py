
"""
Model runner abstraction.
- 'fast' / 'balanced' / 'accurate' profiles map to llama.cpp GGUF settings (or transformers if enabled).
- In this MVP, we simulate generation with a trivial heuristic if no model is configured,
  but the interface is ready for drop-in local LLMs.
"""
import os, re

class ModelProfiles:
    FAST = "fast"
    BALANCED = "balanced"
    ACCURATE = "accurate"

class ModelRunner:
    def __init__(self, profile: str = ModelProfiles.BALANCED):
        self.profile = profile
        # In production: initialize llama-cpp or transformers here based on profile.

    def set_profile(self, profile: str):
        self.profile = profile

    def generate_sql(self, prompt: str) -> str:
        """
        Placeholder generator:
        - If a SELECT is found in the prompt (e.g., in examples), return a sanitized version.
        - Else, synthesize a very simple SELECT using the first table/column references we see.
        Replace with actual LLM inference using llama-cpp-python or transformers.
        """
        # Try to extract a table & a measure from the prompt
        m_table = re.search(r"- ([A-Za-z0-9_]+\.[A-Za-z0-9_]+)", prompt)
        m_col = re.search(r"\.([A-Za-z0-9_]+) \(", prompt)
        table = m_table.group(1) if m_table else "sys.objects"
        col = m_col.group(1) if m_col else "name"
        sql = f"SELECT TOP 500 {col} FROM {table};"
        return sql

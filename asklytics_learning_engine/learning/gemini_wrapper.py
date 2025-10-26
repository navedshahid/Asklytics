from __future__ import annotations

import os
import time
from typing import Optional


class GeminiWrapper:
    """Thin wrapper over google.generativeai with retry and context injection."""

    def __init__(self, model: str | None = None):
        self.model_name = model or os.getenv("LEARN_GEMINI_MODEL", "gemini-1.5-pro")
        self._model = None

    def _model_instance(self):
        import google.generativeai as genai  # type: ignore

        if self._model is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY is not set")
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(self.model_name)
        return self._model

    @staticmethod
    def _prompt_for_generate(prompt: str, context: str) -> str:
        return (
            "### Instruction: Generate valid T-SQL for SQL Server\n"
            "Constraints: Use only T-SQL; prefer SELECT TOP (N). No DDL/DML.\n\n"
            f"Context:\n{context}\n\n"
            f"User query: {prompt}\nSQL:"
        )

    @staticmethod
    def _prompt_for_repair(prompt: str, error_msg: str, context: str) -> str:
        return (
            "### Instruction: Repair the T-SQL to be valid for SQL Server.\n"
            f"Validation error: {error_msg}\n\n"
            f"Context:\n{context}\n\n"
            f"User query: {prompt}\nRepaired SQL:"
        )

    def _call_with_retry(self, text: str, retries: int = 3, backoff: float = 1.5) -> str:
        last = None
        for i in range(retries):
            try:
                mdl = self._model_instance()
                resp = mdl.generate_content(text)
                return (resp.text or "").strip()
            except Exception as e:  # pragma: no cover - relies on API
                last = e
                time.sleep(backoff ** (i + 1))
        raise RuntimeError(f"Gemini call failed after retries: {last}")

    def generate_sql(self, prompt: str, context: str) -> str:
        text = self._prompt_for_generate(prompt, context)
        return self._call_with_retry(text)

    def repair_sql(self, prompt: str, error_msg: str, context: str) -> str:
        text = self._prompt_for_repair(prompt, error_msg, context)
        return self._call_with_retry(text)


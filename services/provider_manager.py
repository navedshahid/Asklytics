from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Protocol, Tuple


class Provider(Protocol):
	"""LLM provider protocol for SQL generation and summarization."""

	def name(self) -> str:
		...

	def generate_sql(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
		"""
		Generate SQL for the given prompt and optional MDL/schema context.
		Returns (sql_string, metadata)
		"""
		...


class GeminiProvider:
	def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, base_url: Optional[str] = None):
		self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
		self.model = model or os.getenv("GEMINI_MODEL_FOR_SQL", "gemini-1.5-flash-latest")
		self.base_url = base_url or os.getenv("GEMINI_BASE_API_URL", "https://generativelanguage.googleapis.com/v1beta/models")

	def name(self) -> str:
		return "gemini"

	def generate_sql(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
		# Lightweight placeholder: defer to existing app route pipeline externally.
		# Here we just package the request. Real implementation would call Gemini REST.
		metadata = {
			"provider": self.name(),
			"model": self.model,
			"used_context": bool(context),
		}
		# Return empty SQL and metadata; caller can decide to route to existing flow.
		return "", metadata


class ClaudeProvider:
	def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
		self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
		self.model = model or os.getenv("CLAUDE_MODEL_FOR_SQL", "claude-3-5-sonnet-latest")
		self._client = None
		try:
			# Lazy import to avoid hard dependency when not configured
			import anthropic  # type: ignore
			self._client = anthropic.Anthropic(api_key=self.api_key)
		except Exception:
			self._client = None

	def name(self) -> str:
		return "claude"

	def generate_sql(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
		metadata = {
			"provider": self.name(),
			"model": self.model,
			"used_context": bool(context),
			"status": "skipped" if self._client is None else "attempted",
		}
		if self._client is None:
			return "", metadata
		try:
			ctx_str = "" if not context else "\n\nContext:\n" + str(context)
			messages = [
				{"role": "user", "content": f"Generate a safe, dialect-correct SQL query.\nPrompt: {prompt}{ctx_str}"}
			]
			resp = self._client.messages.create(model=self.model, max_tokens=2048, temperature=0.2, messages=messages)
			text = "".join([b.text for b in resp.content if getattr(b, "type", "") == "text"])  # type: ignore
			return text.strip(), metadata
		except Exception as e:
			metadata["error"] = str(e)
			return "", metadata


class ProviderManager:
	"""Simple provider manager supporting ensemble calls."""

	def __init__(self, providers: Optional[List[Provider]] = None):
		self._providers: List[Provider] = providers or self._load_default_providers()

	def _load_default_providers(self) -> List[Provider]:
		loaded: List[Provider] = []
		# Always include Gemini stub to keep parity with current flow
		loaded.append(GeminiProvider())
		# Include Claude if API key present
		if os.getenv("ANTHROPIC_API_KEY"):
			loaded.append(ClaudeProvider())
		return loaded

	def providers(self) -> List[Provider]:
		return list(self._providers)

	def generate_sql_ensemble(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
		"""
		Ask all providers for SQL, return the best candidate with metadata and all attempts.
		Current selection logic prefers first non-empty SQL; future work can add voting.
		"""
		attempts: List[Dict[str, Any]] = []
		best_sql = ""
		best_meta: Dict[str, Any] = {}
		for p in self._providers:
			sql, meta = p.generate_sql(prompt, context)
			meta = {**meta, "provider": p.name()}
			attempts.append({"provider": p.name(), "meta": meta, "sql": sql})
			if not best_sql and sql:
				best_sql, best_meta = sql, meta
		# Return possibly empty SQL to allow upstream fallbacks
		return best_sql, best_meta, attempts

"""
Semantic Validator

Validates SQL against simple semantic rules (placeholder).
"""
from __future__ import annotations

from typing import Dict, Any
from services.sql_service import validate_tsql


class SemanticValidator:
    def __init__(self, semantic_model: Dict[str, Any], tribal_rules: Dict[str, Any]):
        self.model = semantic_model or {}
        self.rules = tribal_rules or {}

    def validate(self, sql: str) -> bool:
        # Placeholder: just ensure it parses as T-SQL
        return validate_tsql(sql)

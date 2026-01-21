"""
SQL Compiler Agent

Converts a logical plan into deterministic T-SQL using the semantic model.
This is a placeholder that maps measures/dimensions to SELECT/GROUP BY.
"""
from __future__ import annotations

from typing import Dict, Any
from services.sql_service import transpile_to_tsql, inject_safety_top


class SQLCompiler:
    def __init__(self, semantic_model: Dict[str, Any]):
        self.model = semantic_model or {}

    def compile(self, logical_plan: Dict[str, Any]) -> str:
        entity_name = logical_plan.get("entity")
        entity = None
        for e in self.model.get("entities", []):
            if e.get("entity") == entity_name:
                entity = e
                break
        if not entity:
            return ""
        measures = logical_plan.get("measures") or []
        dimensions = logical_plan.get("dimensions") or []
        select_parts = []
        group_parts = []
        for d in dimensions:
            select_parts.append(f"[{d}]")
            group_parts.append(f"[{d}]")
        for m in measures:
            select_parts.append(f"SUM([{m}]) AS [{m}]")
        source = entity.get("source_table") or entity_name
        sql = f"SELECT TOP (1000) {', '.join(select_parts)} FROM {source}"
        if group_parts and measures:
            sql += f" GROUP BY {', '.join(group_parts)}"
        return inject_safety_top(transpile_to_tsql(sql))

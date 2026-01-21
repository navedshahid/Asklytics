"""
Planner Agent v2

Translates natural language + semantic model + tribal rules into a logical plan.
This is a minimal placeholder that selects an entity by matching table names.
"""
from __future__ import annotations

from typing import Dict, Any, List
import re


class PlannerAgentV2:
    def __init__(self, semantic_model: Dict[str, Any], tribal_rules: Dict[str, Any] | None = None):
        self.model = semantic_model or {}
        self.rules = tribal_rules or {}

    def plan(self, question: str) -> Dict[str, Any]:
        entities = self.model.get("entities", [])
        chosen = None
        for ent in entities:
            name = (ent.get("entity") or "").lower()
            if name and name in question.lower():
                chosen = ent
                break
        if not chosen and entities:
            chosen = entities[0]
        measures = [m["name"] for m in chosen.get("measures", [])][:3] if chosen else []
        dimensions = [d["name"] for d in chosen.get("dimensions", [])][:3] if chosen else []
        return {
            "entity": chosen.get("entity") if chosen else None,
            "measures": measures,
            "dimensions": dimensions,
            "question": question,
        }


def load_semantic_model(path: str = "semantic/semantic_model.yaml") -> Dict[str, Any]:
    import yaml
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_tribal_rules(path: str = "semantic/tribal_rules.yaml") -> Dict[str, Any]:
    import yaml
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

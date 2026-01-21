import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
import yaml

logger = logging.getLogger("AskLytics-Tribal")


class TribalKnowledgeEngine:
    """Engine for capturing and applying business logic/rules from tribal knowledge."""
    
    def __init__(self, storage_path: str = "data/tribal_knowledge.json", yaml_path: str = "semantic/tribal_rules.yaml"):
        self.storage_path = Path(storage_path)
        self.yaml_path = Path(yaml_path)
        self.rules = self._load_rules()

    def _load_rules(self) -> List[Dict[str, Any]]:
        if not self.storage_path.exists():
            return []
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def save_rule(self, rule: str, context: Optional[str] = None):
        """Save a new business rule."""
        self.rules.append({"rule": rule, "context": context})
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.rules, f, indent=2)
        self._write_yaml()

    def _write_yaml(self):
        data = {
            "global_filters": [r["rule"] for r in self.rules if not r.get("context")],
            "contextual_rules": self.rules,
        }
        self.yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False)

    def get_rules_context(self) -> str:
        """Format rules for inclusion in the Agent prompt."""
        if not self.rules:
            return ""
        
        context = "### BUSINESS RULES (Tribal Knowledge)\n"
        for i, r in enumerate(self.rules, 1):
            context += f"{i}. {r['rule']}\n"
        return context + "\n"


"""
Catalog loader offering simple APIs to read artifacts.
"""
import json, os
from pathlib import Path

class CatalogLoader:
    def __init__(self, base_dir="./catalog/artifacts"):
        self.base = Path(base_dir)
        self.tables = self._load("tables.json").get("tables",[])
        self.columns = self._load("columns.json").get("columns",[])
        self.relationships = self._load("relationships.json").get("relationships",[])
        self.dictionary = self._load("dictionary.json")
        self.version = self._load("version.json")

    def _load(self, name: str):
        p = self.base/name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def list_tables(self):
        return self.tables

    def list_columns(self):
        return self.columns

    def list_relationships(self):
        return self.relationships

    def get_version(self):
        return self.version or {}

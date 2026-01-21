"""
Semantic Modeling Engine

Converts raw discovery output into a semantic_model.yaml contract that encodes
entities, measures, dimensions, and required filters. This is a placeholder
implementation that maps tables/columns into a basic semantic contract; it can
be extended with richer heuristics and user overrides.
"""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Dict, Any, List


class SemanticModelEngine:
    def __init__(self, output_path: str = "semantic/semantic_model.yaml"):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def build_model(self, discovery_manifest: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a minimal semantic model from discovery manifest.
        discovery_manifest structure (expected):
            {
              "tables": [
                {"name": "dbo.Table", "columns": [{"name":"col","type":"int"}, ...]},
                ...
              ],
              "fks": [
                {"from": "[dbo].[A].[col]", "to": "[dbo].[B].[id]"},
                ...
              ]
            }
        """
        entities: List[Dict[str, Any]] = []
        tables = discovery_manifest.get("tables", [])
        fks = discovery_manifest.get("fks", [])

        fk_map: Dict[str, List[str]] = {}
        for fk in fks:
            src = fk.get("from")
            tgt = fk.get("to")
            if src and tgt:
                fk_map.setdefault(src.split("].[")[0], []).append(tgt)

        for tbl in tables:
            tname = tbl.get("name")
            cols = tbl.get("columns", [])
            entity = {
                "entity": tname,
                "source_table": tname,
                "grain": "one_row_per_source_row",
                "measures": [],
                "dimensions": []
            }
            for col in cols:
                cname = col.get("name")
                ctype = (col.get("type") or "").lower()
                if ctype in ("int", "bigint", "decimal", "numeric", "float", "real", "money"):
                    entity["measures"].append({"name": cname, "expression": cname})
                # treat everything as dimension for now
                entity["dimensions"].append({"name": cname, "column": cname})
            entities.append(entity)

        model = {"entities": entities, "fks": fks}
        self._write(model)
        return model

    def _write(self, model: Dict[str, Any]) -> None:
        with open(self.output_path, "w", encoding="utf-8") as f:
            yaml.dump(model, f, sort_keys=False)


def load_discovery_manifest(path: str = "semantic/schema_manifest.json") -> Dict[str, Any]:
    import json
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


class LayoutStore:
	"""File-based storage for semantic MDL graph layouts.

	Layouts are stored under semantic/mdl_layout/<graph_name>.json
	A layout document is an arbitrary JSON with at least:
	{
		"version": "v1",
		"nodes": [...],
		"edges": [...],
		"groups": [...]
	}
	"""

	def __init__(self, root: str = "semantic/mdl_layout"):
		self.root = Path(root)
		self.root.mkdir(parents=True, exist_ok=True)

	def _safe_name(self, name: str) -> str:
		if not name:
			raise ValueError("name required")
		if any(c in name for c in ("/", "\\", "..")):
			raise ValueError("invalid name")
		return name

	def path_for(self, name: str) -> Path:
		safe = self._safe_name(name)
		return self.root / f"{safe}.json"

	def get(self, name: str) -> Optional[Dict[str, Any]]:
		p = self.path_for(name)
		if not p.exists():
			return None
		with open(p, "r", encoding="utf-8") as f:
			return json.load(f)

	def put(self, name: str, doc: Dict[str, Any]) -> Dict[str, Any]:
		# Minimal validation
		if not isinstance(doc, dict):
			raise ValueError("layout must be an object")
		if "version" not in doc:
			doc["version"] = "v1"
		p = self.path_for(name)
		with open(p, "w", encoding="utf-8") as f:
			json.dump(doc, f, ensure_ascii=False, indent=2)
		return {"status": "success", "name": name, "path": str(p)}

	def delete(self, name: str) -> Dict[str, Any]:
		p = self.path_for(name)
		if p.exists():
			p.unlink()
			return {"status": "success", "name": name}
		return {"status": "not_found", "name": name}

	def list(self) -> Dict[str, Any]:
		items = []
		for f in self.root.glob("*.json"):
			items.append({"name": f.stem, "path": str(f)})
		return {"layouts": items}

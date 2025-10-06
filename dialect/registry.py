# dialect/registry.py
from dataclasses import dataclass
from typing import Protocol

# --- Protocols define what each dialect must implement ---
class CatalogBuilder(Protocol):
    def refresh(self, dsn: str, schemas: list[str] | None, out_dir: str) -> dict: ...

class SQLValidator(Protocol):
    def policies_block(self) -> str: ...
    def assert_safe(self, sql: str) -> None: ...
    def patch_sql(self, sql: str) -> str: ...

class Executor(Protocol):
    def execute(self, sql: str): ...

@dataclass
class DialectSpec:
    name: str              # "tsql" | "postgres" | "mysql"
    catalog_builder: CatalogBuilder
    prompt_template: str   # e.g., "tsql.md", "pg.md", "mysql.md"
    validator: SQLValidator
    executor: Executor

# Global registry
REGISTRY: dict[str, DialectSpec] = {}
def register(spec: DialectSpec):
    REGISTRY[spec.name] = spec

def get(name: str) -> DialectSpec:
    if name not in REGISTRY:
        raise ValueError(f"Unsupported dialect: {name}")
    return REGISTRY[name]

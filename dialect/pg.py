from dialect.registry import DialectSpec, register
from catalog.refresh_catalog_pg import refresh_catalog as pg_refresh
from safety.pg_validator import PGValidator
from execution.pg import SafePGExecutor

spec = DialectSpec(
    name="postgres",
    catalog_builder = type("PGCatalog", (), {"refresh": staticmethod(pg_refresh)}),
    prompt_template = "pg.md",
    validator = PGValidator(default_limit=500),
    executor = SafePGExecutor()
)
register(spec)

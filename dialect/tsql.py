# dialect/tsql.py
from dialect.registry import DialectSpec, register
from catalog.refresh_catalog_tsql import refresh_catalog as tsql_refresh
from safety.sql_validator import SQLValidator as TSQLValidator
from execution.tsql import SafeTSQLExecutor

spec = DialectSpec(
    name="tsql",
    catalog_builder = type("TSQLCatalog", (), {"refresh": staticmethod(tsql_refresh)}),
    prompt_template = "tsql.md",
    validator = TSQLValidator(),
    executor = SafeTSQLExecutor()  # uses QP_SQL_DSN env
)
register(spec)

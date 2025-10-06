
"""
CLI for Asklytics.
Provides: serve, refresh-catalog, eval
"""
import click
import uvicorn
from app import app
from catalog.refresh_catalog_tsql import refresh_catalog
from eval.runner import run_eval

@click.group()
def cli():
    pass

@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind address")
@click.option("--port", default=8080, type=int, help="Port")
@click.option("--profile", default="balanced", type=click.Choice(["fast","balanced","accurate"]), help="Model profile")
def serve(host, port, profile):
    """
    Serve the API via Uvicorn (Flask dev server is fine too; Uvicorn is snappier).
    """
    # Bind model profile through environment or a tiny shim; simplest path is to just run app directly.
    # For MVP, we'll just run app with default. You can set profile via POST /ask payload.
    uvicorn.run("app:app", host=host, port=port, reload=False)

@cli.command()
@click.option("--dsn", required=True, help="pyodbc connection string or DSN")
@click.option("--schemas", default="", help="Comma-separated list of schemas to include (default: all visible)")
@click.option("--out", "out_dir", default="./catalog/artifacts", help="Output directory for catalog JSONs and FAISS index")
def refresh_catalog_cmd(dsn, schemas, out_dir):
    """
    Refreshes local catalog (tables/columns/relationships/stats/embeddings).
    """
    schema_list = [s.strip() for s in schemas.split(",") if s.strip()] if schemas else None
    info = refresh_catalog(dsn=dsn, schemas=schema_list, out_dir=out_dir)
    click.echo(f"Refreshed catalog: {info}")

@cli.command()
@click.option("--suite", default="./eval/suites/adventureworks.yaml", help="Path to eval suite YAML")
def eval(suite):
    """
    Runs a small accuracy/latency evaluation suite against the running API or direct components.
    """
    results = run_eval(suite)
    click.echo(results)

if __name__ == "__main__":
    cli()

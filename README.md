
# Asklytics — MVP (Day-30)
**One-click, on-prem “Ask your data” copilot** for SQL Server (first).  
This scaffold implements the core flow: Catalog → Retrieval → NL→SQL → Safe Execution → Results/Audit.

> Built for air‑gapped SMEs. Read-only by design. T-SQL first.

## Quickstart
```bash
# 1) Create venv and install
python -m venv .venv && . .venv/Scripts/activate  # Windows
pip install -r requirements.txt

# 2) Refresh catalog (uses pyodbc DSN or connection string)
python cli.py refresh-catalog --dsn "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=AdventureWorks2017;Trusted_Connection=yes;" --schemas Sales,Person,Production

# 3) Serve API
python cli.py serve --host 0.0.0.0 --port 8080 --profile balanced

# 4) Ask a question
curl -X POST http://localhost:8080/ask -H "Content-Type: application/json" -d '{"question":"Top 10 customers by total sales last quarter"}'
```

## Layout
- `app.py` — Flask API: `/ask`, `/sql/validate`, `/catalog/refresh`, `/health`
- `cli.py` — CLI wrapper (serve, refresh-catalog, eval)
- `catalog/` — builders & loaded JSON/FAISS artifacts
- `retrieval/` — hybrid schema selection (FAISS + BM25 + relationship graph)
- `prompting/` — Jinja prompt templates & few-shot examples
- `safety/` — SQL validator (AST + rule checks) and patcher
- `execution/` — safe T-SQL execution with caps, timeouts, and audit
- `eval/` — micro evaluation harness on example suites
- `docs/Solution_Design.md` — solution design document

AskLytics – Agent Guide (agent.md)
0) TL;DR (for Codex)

Product: Self-learning, explainable AI analyst over enterprise DBs (D365-friendly).

Stack: Flask + Gemini (LLM) + SQLite (dev) → pg/postgres+pgvector (later) + FAISS + plain HTML/JS.

Must-haves: ISO-27001-aligned PII masking by default, audit logs (append-only), feedback loop, hybrid validation, governance & ROI dashboards.

Never break: Existing endpoints, masking defaults, role checks, migrations.

1) Project Overview

Purpose
AskLytics turns natural-language questions into validated SQL, executes safely, and returns business-readable insights with provenance (tables/joins) and a confidence score. It learns locally from user feedback; no base-model retraining required.

High-level Architecture

[UI: index.html/settings.html/dashboard] 
      ↓
[Flask API: /api/ask, /api/insight/*, /api/learn/*, /api/gov/*, /api/roi/*]
      ↓
[Orchestrator] ──→ [Gemini wrapper] → SQL candidates
      │                           └→ (Summarize/Explain endpoints)
      ├─→ [Hybrid Validator] (rules + semantic review + shadow checks)
      ├─→ [Safe Executor] (LIMIT/TOP, timeouts)
      ├─→ [Experience Store + FAISS] (learning memory & retrieval)
      ├─→ [Feedback Manager] (user-verified correctness → FAISS)
      └─→ [Audit Logger] (ISO 27001; masked by default)

[Governance & ROI Dashboard] reads: xp, audit_log, feedback → KPIs & trends


Key Guarantees

Trust: Hybrid validation + confidence scoring + user-verified feedback.

Explainability: Provenance string + “Explain in 2 sentences.”

Compliance: PII masked by default; unmask only for authorized roles and always audited.

2) Code Style & Conventions

Python

PEP-8, type hints required on public functions.

Docstrings (Google or NumPy style).

Lint/format: ruff + black (line length 100).

Prefer dependency injection for DB connections and providers.

Module naming: snake_case.py; classes PascalCase; functions/vars snake_case.

Errors: raise typed exceptions in core; Flask layer returns JSON error contracts.

JavaScript (vanilla)

Modules in /static/js. Use ES6 features.

Naming: camelCase for vars/functions; constants SCREAMING_SNAKE_CASE.

No frameworks; use Chart.js via CDN only.

HTML/CSS

Keep semantic HTML; no inline styles; put extras in /static/css.

Minimal utility classes; prefer small component CSS (cards, tabs, badges).

Commits & Branching

Conventional commits: feat:, fix:, refactor:, chore:, docs:, test:

Branches: feature/<short-name>, fix/<short-name>.

Each PR: include migration steps, test plan, and acceptance criteria.

API Contracts

JSON only; {"ok": true|false, "data": ..., "error": {"code": "...", "message": "..."}}

Never return raw stack traces; log them server-side.

3) Build, Run & Test Commands

Environment

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set GEMINI_API_KEY, CHAT_SESSION_LIMIT, etc.


Run (dev)

flask --app app.py run
# or: python app.py


Lint/Format/Types

ruff check .
black .
mypy .


Unit & Integration Tests

pytest -q
# optional markers: -m "validator or roi or feedback"


Seed & Migrations (SQLite)

python scripts/run_migrations.py     # applies /migrations/*.sql in order
python scripts/seed_fake_users.py    # optional demo users/roles


Regression Suite (if present)

curl -X POST http://localhost:5000/api/learn/regression/run

4) Project Structure (What lives where)
/app.py                          # Flask app & routes wiring
/orchestrator.py                 # main flow: prompt → SQL → validate → execute → persist
/app_meta_patch.py               # metadata routes (harvest, schema slice)
/metadata_store.py               # schema access, FK/PK maps, lineage helpers
/metadata_routes.py              # REST around metadata

/learning/
  experience_store.py            # xp table DAO + retrieval
  embedder.py                    # embedding + FAISS index build/query
  validator.py                   # legacy/basic validator
  hybrid_validator.py            # rule + semantic + shadow checks (new)
  validation_rules.py            # schema/FK/group-by checks
  semantic_reviewer.py           # Gemini-based SQL/intent review
  shadow_executor.py             # COUNT/SUM sanity checks (no PII)
  feedback_manager.py            # capture feedback + feed FAISS
  feedback_dao.py                # feedback persistence
  faiss_updater.py               # insert verified examples into FAISS

/governance/
  audit_logger.py                # append-only audit log writer
  masker.py                      # PII masking/redaction
  rbac.py                        # roles & decorators
  policies.py                    # masking/retention/export rules
  dao.py                         # DB abstraction (sqlite now; pg later)

/roi/
  metrics_service.py             # accuracy, pass-rate, usage, time-saved KPIs

/templates/
  index.html                     # chat UI (tabs: Results | Visuals | SQL)
  settings.html                  # config (limits, defaults, governance)
  governance_dashboard.html      # ISO dashboard (auditors/admin)
  partials/insight_panel.html    # Business Mode explainability panel
  partials/feedback_panel.html   # thumbs up/down UI

/static/js/
  asklytics_ui.js                # tabs, charts, summaries, CSV export
  governance_dashboard.js        # ROI/governance charts & tables
  feedback.js                    # feedback submission & state

/static/css/
  asklytics.css                  # badges, cards, layout utils
  governance.css                 # dashboard styles

/migrations/
  001_add_governance.sql
  002_add_indexes.sql
  003_add_confidence.sql
  004_add_feedback.sql
  ...                            # each idempotent; safe on re-run

/data/
  schema.json                    # cached schema slice (dev)
  faiss_index.faiss              # vector store (dev)
/scripts/
  run_migrations.py
  seed_fake_users.py

5) Important Considerations (Read before coding)
Security & ISO 27001

Mask PII by default everywhere (UI, exports, logs). Unmasking:

only for pii_viewer role,

requires explicit toggle + reason,

must create an audit_log record with pii_exposure=1.

Audit logs are append-only. Log actions: prompt_submitted, sql_generated, validation_complete, sql_executed, export_csv, view_unmasked, feedback_submit. Store hashes, not raw payloads.

Secrets: load from .env; never print or commit.

Data retention: purge audit/xp beyond configured days (nightly job) and VACUUM SQLite.

Product Quirks & Contract

Never break these endpoints (contracts already used by UI):

/api/ask*, /api/insight/*, /api/learn/*, /api/gov/*, /api/roi/*, /api/feedback/*.

Session limits: default 5 chat sessions per user (configurable).

Business Mode: when enabled, always call summarize+provenance+confidence; show confidence badge.

Charts: destroy existing Chart.js instance before creating a new one.

Retrieval: include approved, user-verified examples first in few-shot context.

Validator: do not read raw PII rows; use schema + shadow aggregates only.

Deployment Steps (dev)

Apply migrations → python scripts/run_migrations.py

Set .env (GEMINI_API_KEY, CHAT_SESSION_LIMIT, MASKING_MODE, AUDIT_RETENTION_DAYS, …)

Start Flask → flask --app app.py run

(Optional) Seed demo users/roles → python scripts/seed_fake_users.py

Open /dashboard/governance (auditor/admin role) to verify KPIs render.

Future-Proofing (Do not implement unless task requires)

Postgres + pgvector adapter via /governance/dao.py interface (keep code pg-ready).

Provider manager to add OpenAI/Claude later (same method signatures).

Personas/BKG and Auto-MDL: placeholders only.

6) How to Propose & Ship a Change (Template for Codex)

Task Brief

Goal: (one sentence)

Modules touched: (files)

API changes: (new/modified endpoints & JSON)

Migrations: (yes/no + file name)

Security impact: (PII, roles, audit)

Acceptance criteria: (bullet list, measurable)

Tests: (unit/integration; how to run)

Done when

All acceptance criteria pass locally (pytest -q, manual smoke on UI).

ruff, black, mypy clean.

Migrations idempotent and applied.

Audit events confirmed in /api/gov/audit/rollup.

7) Common Commands & Snippets

CSV download (client)

import { toCSV } from '/static/js/asklytics_ui.js';
download('result.csv', toCSV(columns, rows));


Confidence scoring (server)

from services.confidence_scorer import compute
score, label = compute(signals)  # stored in xp.confidence_score/_label


Masking

from governance.masker import mask_row
safe_rows = [mask_row(r, columns, policy) for r in rows]  # default masked


Audit

audit_logger.log_event(user_id, session_id, "sql_executed", sql_id, req_hash, resp_hash,
                       masked=True, pii_exposure=False, provider="gemini",
                       exec_ms=latency, meta={"rows": rowcount, "confidence": score})

8) Known Pitfalls & How to Avoid

Charts overlapping: always currentChart?.destroy() before re-render.

State loss on refresh: restore last session_id and active tab from localStorage.

Unapproved feedback in FAISS: only index verdict='correct' & confidence ≥ 0.7 (and if moderator approval exists in your flow).

PII leaks in exports: exports are masked unless pii_viewer + unmask=true; always audit.

9) Contact & Ownership

Product owner: Naveed Shahid

Security owner: Governance module (RBAC/Masking/Audit)

AI/Validation owner: Learning + Hybrid Validator modules

UI owner: Templates & static assets
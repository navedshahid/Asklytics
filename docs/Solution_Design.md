
# QueryPilot Enterprise — Solution Design (MVP)

**Date:** 2025-09-20 21:46:07Z  
**Author:** Naveed Shahid

## 1. Vision & Scope
Deliver a local, trustworthy NL→SQL assistant for SQL Server that non-technical users can ask business questions to and receive accurate, auditable answers. Air‑gapped friendly, read-only by default, with an upgrade path to GPU acceleration.

## 2. Architecture Overview
**Core services:**
- **Catalog Service:** Extracts schema (tables/columns/PK/FK), light stats, and sample values; writes JSON artifacts and FAISS index. Versioned & checksummed.
- **Retrieval Engine:** Hybrid selection using vectors + lexical match + FK expansion; produces a compact working set of tables/columns.
- **Prompting:** File-based Jinja templates (per dialect) that inject metadata, relationships, and safety policies.
- **NL→SQL Engine:** Pluggable local model runner (llama.cpp GGUF by default); profile switcher (fast/balanced/accurate).
- **Safety (SafeExec):** SQL validator enforces SELECT-only, caps, and join sanity; patched if possible; otherwise rejected.
- **Execution & Audit:** Read-only pool, ROWCOUNT caps, timeouts; SQLite audit trail of prompts, SQL, outcomes.
- **Experience Layer:** Flask API, minimal UI (to be added), CLI, and Admin endpoints.

![High-level Diagram](notional)

## 3. Data Flow
1. **Catalog Refresh:** Admin triggers refresh → `refresh_catalog_tsql.py` connects via pyodbc → writes `tables.json`, `columns.json`, `relationships.json`, `dictionary.json`, `columns.faiss`, `version.json`.
2. **Question Handling (`/ask`):** 
   - HybridSelector picks relevant tables/columns.
   - PromptGenerator renders T-SQL prompt (with safety rules).
   - ModelRunner generates candidate SQL.
   - SQLValidator checks/patches.
   - SafeTSQLExecutor executes with caps; results + metadata returned.
   - AuditLogger records interaction.
3. **Learning Loop:** Future: user approvals feed dictionary weights and few-shots.

## 4. Security Posture
- **Read-only DSN** enforced via environment variable `QP_SQL_DSN`.
- **Validator** blocks DDL/DML, EXEC/MERGE/TRUNCATE, and unsafe CROSS JOIN patterns.
- **Caps:** TOP/ROWCOUNT and timeouts.
- **Visibility Lenses (future):** Role-based column exclusion at retrieval-time.

## 5. Deployment
- Single-host, Python 3.11+.
- Optional Docker Compose.
- No internet needed at runtime (current embedding is hashing-based; replaceable with SentenceTransformer when available).

## 6. Extensibility
- Add `prompting/templates/pg.md` for PostgreSQL, `execution/pg.py` for execution.
- Replace `retrieval/embed.py` with SentenceTransformer and rebuild FAISS.
- Swap `utils/models.py` with llama-cpp or transformers code paths.

## 7. Observability & KPIs
- **Audit DB**: user, question, SQL, success, rows, latency.
- KPIs: first-answer success, approval rate, median latency, active users, coverage.

## 8. Risks & Mitigations
- **Semantic quality of embeddings (MVP):** hashing is weak → plan upgrade to SentenceTransformer.
- **SQL safety bypass via obfuscation:** add AST-based parser in next release.
- **Schema drift:** checksum-based invalidation + scheduled catalog refresh.

## 9. Roadmap (Next 60–90 days)
- GPU path via `transformers`.
- Few-shot learning; dictionary editor UI.
- RBAC & Privacy Lenses; SSO.
- Scheduler & alerts; caching; HA mode.

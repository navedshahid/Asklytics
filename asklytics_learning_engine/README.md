AskLytics Learning Engine (Local)
=================================

Purpose
-------
Local, self-improving accuracy layer for AskLytics using: Gemini API for reasoning, and local feedback memory + FAISS retrieval + validation/reranking. No cloud fine-tuning.

Quick Start
-----------
1) Env vars (.env recommended)

   - GEMINI_API_KEY=your_key
   - LEARN_DB_URL=sqlite:///./learning_store.db
   - LEARN_TOPK=3
   - (optional) ASKLYTICS_ODBC_CONNSTR=Driver={ODBC Driver 17 for SQL Server};Server=HOST;Database=DB;UID=sa;PWD=***

2) Build or run components

   - Feedback UI: python -m asklytics_learning_engine.ui.feedback_ui
   - Nightly jobs (FAISS rebuild): python -m asklytics_learning_engine.main --nightly
   - On-demand index rebuild: python -m asklytics_learning_engine.main --reindex

3) Workflow

   - process_query() retrieves similar examples → builds context → calls Gemini → validates → executes (optional) → scores → saves experience → vectors updated by nightly job.

Architecture
------------
learning/
 - experience_store.py: SQLite (learning_store.db) with table xp
 - embedder.py: SentenceTransformer → FAISS index build/query (data/faiss_index.faiss)
 - gemini_wrapper.py: Gemini calls with retry
 - validator.py: sqlparse checks + metadata presence (mm_asset/mm_column)
 - learning_loop.py: orchestrates generation, validation, execution, scoring
 - nightly_job.py: APScheduler job to recompute accuracy + rebuild FAISS

ui/
 - feedback_ui.py: Minimal Flask app to capture user feedback via /api/learn/feedback

Data
----
data/schema.json, data/meta.json, data/regression_default.json are placeholders. FAISS index persists to data/faiss_index.faiss.

Notes
-----
AskLytics uses Gemini for reasoning but learns locally through feedback memory.


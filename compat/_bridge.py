# compat/_bridge.py
from __future__ import annotations

import os, json, time, re
from typing import Dict, Any, List, Set

import pyodbc
from flask import Blueprint, request, jsonify, Response

# Internal modules
from catalog.loader import CatalogLoader
from retrieval.selector import HybridSelector
from prompting.generator import PromptGenerator
from safety.sql_validator import SQLValidator, ValidationError as SQLValidationError
from execution.tsql import SafeTSQLExecutor
from utils.audit import AuditLogger
from utils.models import ModelRunner, ModelProfiles
from safety.schema_guard import validate_or_patch_sql

# ---------------- Blueprint (THIS is what app.py imports) ----------------
bp = Blueprint("asklytics", __name__, url_prefix="/api")

# ---------------- persistence ----------------
CONFIG_DIR = os.environ.get("GENDS_CONFIG_DIR", "./data")
CONFIG_PATH = os.path.join(CONFIG_DIR, "asklytics_config.json")
TABLE_FILTER_PATH = os.path.join(CONFIG_DIR, "table_filter.json")
os.makedirs(CONFIG_DIR, exist_ok=True)

# ---------------- singletons ----------------
_catalog = CatalogLoader(base_dir="./catalog/artifacts")
_selector = HybridSelector(base_dir="./catalog/artifacts")
_prompt   = PromptGenerator(template_dir="./prompting/templates")
_validator = SQLValidator()
_executor  = SafeTSQLExecutor(audit_path="./storage/audit.sqlite")
_audit     = AuditLogger(db_path="./storage/audit.sqlite")
_model     = ModelRunner(profile=ModelProfiles.BALANCED)

# ---------------- helpers ----------------
def _load_cfg() -> Dict[str, Any]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def _save_cfg(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def _load_db() -> Dict[str, Any]:
    return _load_cfg().get("db", {})

def _save_db(db: Dict[str, Any]) -> None:
    cfg = _load_cfg()
    cfg["db"] = db
    _save_cfg(cfg)

def _load_tables_sel() -> Set[str] | None:
    try:
        with open(TABLE_FILTER_PATH, "r", encoding="utf-8") as f:
            return set((json.load(f).get("tables") or []))
    except Exception:
        return None

def _save_tables_sel(tables: List[str]) -> None:
    with open(TABLE_FILTER_PATH, "w", encoding="utf-8") as f:
        json.dump({"tables": tables}, f, indent=2)

def _installed_sql_drivers() -> List[str]:
    try:
        return pyodbc.drivers()
    except Exception:
        return []

def _driver_token(name: str | None) -> str:
    name = (name or "").strip()
    if not name:
        drivers = _installed_sql_drivers()
        name = "ODBC Driver 18 for SQL Server" if "ODBC Driver 18 for SQL Server" in drivers else "ODBC Driver 17 for SQL Server"
    if name.startswith("{") and name.endswith("}"):
        return f"DRIVER={name}"
    return f"DRIVER={{{name}}}"

def _dsn_from(db: Dict[str, Any]) -> str:
    driver = _driver_token(db.get("driver"))
    server = db["server"].strip()
    database = db["database"].strip()
    base = f"{driver};SERVER={server};DATABASE={database};TrustServerCertificate=yes;"
    if db.get("trusted_connection"):
        return base + "Trusted_Connection=yes;"
    uid = (db.get("uid") or "").strip()
    pwd = (db.get("pwd") or "").strip()
    return base + f"UID={uid};PWD={pwd};"

def _current_dialect() -> str:
    return (_load_cfg().get("dialect") or "tsql").lower()

def _set_dialect(dialect: str) -> None:
    cfg = _load_cfg()
    cfg["dialect"] = dialect.lower()
    _save_cfg(cfg)

# hot-apply DSN if DB already saved
if _load_db():
    os.environ["QP_SQL_DSN"] = _dsn_from(_load_db())

# ---------------- status & info ----------------
@bp.get("/status")
def status():
    faiss_ok = os.path.exists("./catalog/artifacts/columns.faiss")
    return jsonify({
        "database_configured": bool(_load_db()),
        "faiss_index_loaded": faiss_ok,
        "dialect": _current_dialect(),
        "drivers_detected": _installed_sql_drivers()
    })

@bp.get("/db_info")
def db_info():
    db = _load_db()
    if not db:
        return jsonify({"database": None, "server": None, "dialect": _current_dialect()}), 200
    safe = {k: v for k, v in db.items() if k != "pwd"}
    safe["dialect"] = _current_dialect()
    return jsonify(safe), 200

# ---------------- settings: save & test ----------------
@bp.post("/settings/db/test")
def settings_test():
    details = request.get_json(force=True) or {}
    try:
        dsn = _dsn_from(details)
        with pyodbc.connect(dsn, timeout=int(details.get("timeout", 10))):
            pass
        return jsonify({"status": "success", "message": "Connection test successful!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"{e}", "drivers_detected": _installed_sql_drivers()})

@bp.post("/settings/db/save")
def settings_save():
    payload = request.get_json(force=True) or {}
    db = payload.get("db") or {}
    dialect = (payload.get("dialect") or "tsql").lower()
    if not db.get("server") or not db.get("database"):
        return jsonify({"status": "error", "message": "Server and Database are required"}), 400
    _save_db(db)
    _set_dialect(dialect)
    os.environ["QP_SQL_DSN"] = _dsn_from(db)  # hot apply
    return jsonify({"status": "success", "message": "Configuration saved", "dialect": dialect})

# ---------------- table list & selection ----------------
def _db_tables_internal():
    try:
        db = _load_db()
        if not db: return []
        dsn = _dsn_from(db)
        with pyodbc.connect(dsn, timeout=10) as cn:
            rows = cn.cursor().execute("""
                SELECT s.name AS schema_name, t.name AS table_name
                FROM sys.tables t
                JOIN sys.schemas s ON s.schema_id = t.schema_id
                ORDER BY s.name, t.name
            """).fetchall()
        return [{"name": f"{r[0]}.{r[1]}"} for r in rows]
    except Exception:
        return []

@bp.get("/db/tables")
def db_tables():
    db = _load_db()
    if not db:
        return jsonify({"status": "error", "message": "Configure DB first"}), 400
    try:
        tables = _db_tables_internal()
        sel = _load_tables_sel() or set()
        out = [{"name": t["name"], "selected": t["name"] in sel} for t in tables]
        return jsonify({"status": "success", "tables": out})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.post("/catalog/tables/save")
def catalog_tables_save():
    payload = request.get_json(force=True) or {}
    selected = payload.get("tables") or []
    legit = {t["name"] for t in (_db_tables_internal() or [])}
    clean = [t for t in selected if t in legit] if legit else selected
    _save_tables_sel(clean)
    return jsonify({"status": "success", "count": len(clean)})

# ---------------- build & reload ----------------
@bp.post("/training/run")
def training_run():
    from catalog.refresh_catalog_tsql import refresh_catalog
    db = _load_db()
    if not db:
        return jsonify({"status": "error", "message": "Configure DB first"}), 400
    dsn = _dsn_from(db)
    allow = _load_tables_sel()
    try:
        info = refresh_catalog(dsn=dsn, schemas=None, out_dir="./catalog/artifacts", allowed_tables=allow)
        return jsonify({"status": "success", "info": info})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.post("/faiss/reload")
def faiss_reload():
    global _catalog, _selector
    _catalog = CatalogLoader(base_dir="./catalog/artifacts")
    _selector = HybridSelector(base_dir="./catalog/artifacts")
    return jsonify({"status": "success", "message": "Knowledge base reloaded"})

@bp.get("/model/info")
def model_info():
    return jsonify({
        "path": os.environ.get("QP_MODEL_PATH"),
        "ctx": os.environ.get("QP_MODEL_CTX"),
        "gpu_layers": os.environ.get("QP_MODEL_NGPU"),
    })

# ---------------- SSE ask/stream ----------------
def _sse(obj: Dict[str, Any]) -> str:
    return "data: " + json.dumps(obj) + "\n\n"

@bp.post("/ask/stream")
def ask_stream():
    payload = request.get_json(force=True) or {}
    q = (payload.get("question") or "").strip()
    user_id = payload.get("user_id") or "anonymous"
    if not q:
        return jsonify({"error": "question is required"}), 400

    def generate():
        try:
            allow = _load_tables_sel()
            retr = _selector.select(q, k_tables=6, k_columns=24, allow_tables=allow)
            prompt = _prompt.render_tsql(question=q, retrieval=retr, policies=_validator.policies_block())
        except Exception as ex:
            yield _sse({"type": "error", "data": {"message": f"Template/retrieval error: {ex}"}})
            return

        # (Optional) send a little fake token stream to keep UI lively
        cut1 = max(1, len(prompt)//3); cut2 = max(2, 2*len(prompt)//3)
        for cut in (cut1, cut2, len(prompt)):
            yield _sse({"type": "token", "data": {"value": prompt[:cut]}})
            time.sleep(0.02)

        # LLM
        sql = _model.generate_sql(prompt)  # <-- requires generate_sql to exist
        try:
            # Schema guard first (ensures only allowed tables/cols)
            ok, sql2, reasons = validate_or_patch_sql(sql, retr)
            if not ok:
                yield _sse({"type":"error","data":{"message":"Schema guard blocked SQL","reasons":reasons,"sql":sql}})
                return
            sql = sql2
            # Safety validator (TOP/ROWCOUNT, etc.)
            _validator.assert_safe(sql)
        except SQLValidationError:
            sql = _validator.patch_sql(sql)

        yield _sse({"type":"sql_complete","data":{"query": sql}})

        # reject quoted-sql mistakes
        if re.match(r"^\s*select\s+N?'.*'\s*;?\s*$", sql, flags=re.I | re.S):
            yield _sse({"type": "error", "data": {"message": "Model returned quoted SQL text."}})
            return

        # Execute
        try:
            dsn = _dsn_from(_load_db())
            df, meta = _executor.execute(sql, dsn_override=dsn)
            _audit.log(user_id, q, sql, success=True, rows=meta.get("rowcount", 0))
            yield _sse({"type": "result",
                        "data": {"columns": list(df.columns),
                                 "data": df.to_dict(orient="records"),
                                 "meta": meta}})
        except Exception as ex:
            _audit.log(user_id, q, sql, success=False, reasons=[str(ex)])
            yield _sse({"type": "error", "data": {"message": str(ex)}})

    return Response(generate(), mimetype="text/event-stream")
# safe wrapper so UI never crashes if ModelRunner lacks generate_sql
def _generate_sql_safe(prompt: str) -> str:
    gen = getattr(_model, "generate_sql", None)
    if callable(gen):
        return gen(prompt)
    # last-resort stub
    import re
    m_table = re.search(r"- ([A-Za-z0-9_]+\.[A-Za-z0-9_]+)", prompt)
    m_col = re.search(r"\.([A-Za-z0-9_]+) \(", prompt)
    table = m_table.group(1) if m_table else "sys.objects"
    col = m_col.group(1) if m_col else "name"
    return f"SELECT TOP 50 {col} FROM {table};"


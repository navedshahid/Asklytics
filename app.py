# app.py (Final, Simplified, and Robust Version)
from __future__ import annotations

from pathlib import Path
import json, os, tempfile, time, re, logging, decimal
from datetime import datetime, date, time as dtime, timezone
from typing import Generator, Optional
from contextlib import contextmanager
from queue import Queue, Empty
from threading import Lock, Thread

import pyodbc
import numpy as np
import faiss
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, redirect, url_for, Response, stream_with_context, send_file
from flask_cors import CORS
from waitress import serve
from FlagEmbedding import BGEM3FlagModel
from llama_cpp import Llama
import atexit
import uuid
import time
import json as _json
try:
    import redis as _redis
except Exception:
    _redis = None

# local
try:
    from sql_dialect_guard import enforce_tsql, contains_postgresisms
except Exception:
    # graceful fallback (no-ops that just pass through the SQL)
    def enforce_tsql(sql: str, dialect: str = "tsql", mode: str = "translate") -> str:
        return sql
    def contains_postgresisms(sql: str) -> bool:
        return False
from app_meta_patch import AppMetaPatch  # metadata integration
from metrics import compute_summary as metrics_compute_summary, persist_regression_result
try:
    from roi import metrics_service as roi_metrics
except Exception:
    roi_metrics = None
try:
    from asklytics_learning_engine.learning import feedback_manager as fb_mgr
    from asklytics_learning_engine.learning import feedback_dao as fb_dao
except Exception:
    fb_mgr = None
    fb_dao = None
import audit_logger
from thread_store import ThreadStore
try:
    from asklytics_learning_engine.learning import hybrid_validator as _hybrid
    from asklytics_learning_engine.learning import validation_rules as _vrules
except Exception:
    _hybrid = None
    _vrules = None
from typing import List, Dict, Any

try:
    import pandas as _pd  # optional
except Exception:
    _pd = None

# --- Gemini helpers (lightweight wrappers) ---
def _summarize_result_head(columns: List[str], rows: List[dict], query: str | None = None) -> Dict[str, Any]:
    try:
        # If pandas is available, create a tiny head; else fallback heuristic
        head_text = ''
        if _pd is not None and rows:
            df = _pd.DataFrame(rows)[:20]
            head_text = df.to_string(index=False)
        # Simple heuristic summary when LLM unavailable
        nrows = len(rows)
        ncols = len(columns)
        summary = f"Result has {nrows} rows and {ncols} columns."
        bullets = []
        # Try first numeric column
        num_cols = [c for c in columns if any(isinstance(r.get(c), (int, float)) for r in rows[:10])]
        if num_cols:
            c = num_cols[0]
            vals = [r.get(c) for r in rows if isinstance(r.get(c),(int,float))]
            if vals:
                bullets.append(f"Avg {c}: {sum(vals)/len(vals):.2f}")
        return {"summary": summary, "bullets": bullets}
    except Exception:
        return {"summary": "", "bullets": []}

def _plain_provenance(sql: str, validator_signals: Dict[str, Any] | None = None) -> str:
    try:
        # Prefer structured signals when present
        if validator_signals:
            t = validator_signals.get('tables_used') or []
            joins = validator_signals.get('join_keys') or []
            filt = validator_signals.get('filters') or []
            parts = []
            if t: parts.append(" from " + ", ".join(t))
            if joins:
                j = joins[0]
                parts.append(f" joined on {j.get('left')} = {j.get('right')}")
            if filt:
                f = filt[0]
                parts.append(f" where {f.get('field')} {f.get('op')} {f.get('value')}")
            return ("Insight comes" + "".join(parts)).strip()
        # Fallback: simple table extraction
        m = re.findall(r"(?i)(?:from|join)\s+([\w\[\]\.]+)", sql or "")
        if m:
            tbls = ", ".join({x.strip('[]') for x in m})
            return f"Insight comes from {tbls}."
        return "Provenance unavailable."
    except Exception:
        return "Provenance unavailable."

def _confidence_score(payload: Dict[str, Any]) -> Dict[str, Any]:
    v = payload.get('validator') or {}
    ex = payload.get('execution') or {}
    base = 0.5
    if v.get('all_ok') or (v.get('fk_ok') and v.get('group_by_ok')):
        base += 0.2
    rows = ex.get('rows') or 0
    if isinstance(rows, (int, float)) and rows > 0:
        base += 0.15
    if (ex.get('latency_ms') or 0) < 1000:
        base += 0.05
    if (v.get('anomalies') or []):
        base -= 0.2
    base = max(0.0, min(1.0, float(base)))
    label = 'High' if base >= 0.8 else ('Medium' if base >= 0.6 else 'Low')
    reasons = []
    if rows == 0: reasons.append('empty result')
    if v.get('fk_ok'): reasons.append('FK match ok')
    if v.get('group_by_ok'): reasons.append('group-by valid')
    return {"score": base, "label": label, "reasons": reasons}

def _run_hybrid_validation(sql: str, question: str):
    try:
        if not _hybrid or not _vrules:
            return None
        schema = _vrules.load_schema_metadata()
        # Use a short-lived connection from the pool; shadow path runs COUNT(*) only
        with get_db_connection() as conn:
            return _hybrid.validate(sql, question, schema, conn)
    except Exception:
        return None
# Learning engine (metrics + regression)
try:
    from asklytics_learning_engine.learning import eval_service as learn_eval
    from asklytics_learning_engine.learning.regression import run_suite as learn_run_suite
    from asklytics_learning_engine.learning import experience_store as xp
    from asklytics_learning_engine.learning.nightly_job import recompute_indices as learn_reindex
except Exception:
    learn_eval = None
    xp = None
    learn_reindex = None
    def learn_run_suite(*args, **kwargs):
        return {"summary": {"passed": 0, "failed": 0, "duration_ms": 0}, "results": []}
app = Flask(__name__)
app.url_map.strict_slashes = False      # optional, avoids / vs // issues

#  Register the blueprint BEFORE starting the server




load_dotenv()

try:
    import torch
except Exception:  # torch optional
    torch = None


# ---------- Paths & Logging ----------
APP_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = Path(os.getenv("GENDS_CONFIG_DIR", APP_ROOT / "data"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "asklytics_config.json"
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("GenDS")

# ---------- Utility Functions ----------
def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); fd, tmp_path = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent)); os.close(fd); tmp = Path(tmp_path)
    try:
        with open(tmp, "w", encoding="utf-8") as f: json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path); logger.info(f"Saved config to: {path}")
    except Exception as e: logger.error(f"Failed to save config at {path}: {e}", exc_info=True); raise
    finally:
        try:
            if tmp.exists(): tmp.unlink(missing_ok=True)
        except Exception: pass

# ---------- Config Manager (Simplified) ----------
class ConfigManager:
    def __init__(self):
        self._lock = Lock()
        self._config = {
            "db": {"driver": os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server"), "server": None, "database": None, "uid": None, "pwd": None, "timeout": 15, "configured": False},
            "llm": {"model_path": os.getenv("MODEL_PATH"), "n_gpu_layers": int(os.getenv("MODEL_GPU_LAYERS", "0")), "n_ctx": 8096, "n_threads": 8},
            "faiss": {"index_path": "schema.index", "strings_path": "schema_strings.npy", "retrieval_k": 7},
            "gemini": {"api_key": os.getenv("GEMINI_API_KEY"), "base_url": os.getenv("GEMINI_BASE_API_URL", "https://generativelanguage.googleapis.com/v1beta/models"), "model": os.getenv("GEMINI_MODEL_FOR_SQL", "gemini-1.5-flash-latest")},
            "app": {
                "env": os.getenv("FLASK_ENV", "development"),
                "inference": os.getenv("ASKLYTICS_INFERENCE", "gemini"),
                "auto_log_learning": True,
                "auto_summarize": False,
                "chat_session_limit": int(os.getenv("CHAT_SESSION_LIMIT", "5")),
            },
            "selection": {"tables": []}
        }
    def get(self, section: str) -> dict:
        with self._lock: return self._config.get(section, {}).copy()
    def update_db_config(self, db_details: dict) -> None:
        with self._lock:
            self._config["db"].update(db_details); self._config["db"]["configured"] = True
            # SIMPLIFIED: Save the full DB config, including password.
            write_json_atomic(CONFIG_FILE, {"db": self._config["db"], "selection": self._config.get("selection", {"tables": []}), "app": self._config.get("app", {})});
            logger.info(f"DB config updated and saved for server={self._config['db']['server']}")
    def is_db_configured(self) -> bool:
        with self._lock: return bool(self._config["db"]["configured"])
    def get_selected_tables(self) -> list:
        with self._lock:
            sel = self._config.get("selection", {}).get("tables", [])
            return list(sel) if isinstance(sel, list) else []
    def set_selected_tables(self, tables: list) -> None:
        if not isinstance(tables, list):
            tables = []
        with self._lock:
            self._config.setdefault("selection", {})["tables"] = [str(t) for t in tables]
            write_json_atomic(CONFIG_FILE, {"db": self._config["db"], "selection": self._config["selection"], "app": self._config.get("app", {})})
            logger.info("Saved selected tables: %s", len(self._config["selection"]["tables"]))
    def load_from_file(self) -> bool:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f: saved = json.load(f)
            with self._lock:
                if "db" in saved:
                    # SIMPLIFIED: Load the entire saved DB config, including password.
                    self._config["db"].update(saved["db"])
                if "selection" in saved and isinstance(saved["selection"], dict):
                    self._config.setdefault("selection", {}).update(saved["selection"])
                if "app" in saved and isinstance(saved["app"], dict):
                    self._config.setdefault("app", {}).update(saved["app"])
            logger.info(f"Loaded config from {CONFIG_FILE}"); return True
        except FileNotFoundError: logger.info(f"No persisted config found at {CONFIG_FILE}"); return False
        except Exception as e: logger.error(f"Error loading config: {e}", exc_info=True); return False

    # Inference mode helpers
    def get_inference_mode(self) -> str:
        with self._lock:
            mode = (self._config.get("app", {}).get("inference") or "gemini").lower()
            return mode if mode in ("local", "gemini") else "gemini"
    def set_inference_mode(self, mode: str) -> None:
        mode = (mode or "").lower()
        if mode not in ("local", "gemini"):
            raise ValueError("inference must be 'local' or 'gemini'")
        with self._lock:
            self._config.setdefault("app", {})["inference"] = mode
            write_json_atomic(CONFIG_FILE, {"db": self._config["db"], "selection": self._config.get("selection", {}), "app": self._config["app"]})
            logger.info("Saved inference mode: %s", mode)

    def get_auto_log_learning(self) -> bool:
        with self._lock:
            return bool(self._config.get("app", {}).get("auto_log_learning", True))

    def set_auto_log_learning(self, enabled: bool) -> None:
        with self._lock:
            self._config.setdefault("app", {})["auto_log_learning"] = bool(enabled)
            write_json_atomic(CONFIG_FILE, {"db": self._config["db"], "selection": self._config.get("selection", {}), "app": self._config["app"]})
            logger.info("Saved auto_log_learning: %s", enabled)

    # Auto summarize toggle
    def get_auto_summarize(self) -> bool:
        with self._lock:
            return bool(self._config.get("app", {}).get("auto_summarize", False))

    def set_auto_summarize(self, enabled: bool) -> None:
        with self._lock:
            self._config.setdefault("app", {})["auto_summarize"] = bool(enabled)
            write_json_atomic(CONFIG_FILE, {"db": self._config["db"], "selection": self._config.get("selection", {}), "app": self._config["app"]})
            logger.info("Saved auto_summarize: %s", enabled)

    def get_chat_limit(self) -> int:
        with self._lock:
            return int(self._config.get("app", {}).get("chat_session_limit", 5))

    def set_chat_limit(self, n: int) -> None:
        with self._lock:
            self._config.setdefault("app", {})["chat_session_limit"] = int(max(1, min(50, n)))
            write_json_atomic(CONFIG_FILE, {"db": self._config["db"], "selection": self._config.get("selection", {}), "app": self._config["app"]})
            logger.info("Saved chat_session_limit: %s", n)

config = ConfigManager()
app = Flask(__name__, template_folder="templates")
CORS(app, resources={r"/api/*": {"origins": "*"}})
# ---------- CUDA State ----------
def _cuda_diag() -> dict:
    out = {
        "torch_imported": torch is not None,
        "torch_version": getattr(torch, "__version__", None) if torch else None,
        "cuda_available": bool(torch and torch.cuda.is_available()),
        "cuda_version": getattr(torch.version, "cuda", None) if torch else None,
        "gpu_name": None,
        "gpu_count": 0,
    }
    try:
        if torch and torch.cuda.is_available():
            out["gpu_count"] = torch.cuda.device_count()
            out["gpu_name"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    return out

def _faiss_diag() -> dict:
    info = {"faiss_has_gpu": False, "gpu_count": 0}
    try:
        import faiss
        info["faiss_has_gpu"] = hasattr(faiss, "StandardGpuResources")
        if info["faiss_has_gpu"] and hasattr(faiss, "get_num_gpus"):
            info["gpu_count"] = faiss.get_num_gpus()
    except Exception:
        pass
    return info

# ... (Global State is unchanged) ...
# connection_pool: Optional["ConnectionPool"] = None; faiss_index: Optional[faiss.Index] = None; knowledge_strings: Optional[np.ndarray] = None; embedder: Optional[SentenceTransformer] = None; llm: Optional[Llama] = None
connection_pool: Optional["ConnectionPool"] = None
faiss_index: Optional[faiss.Index] = None
knowledge_strings: Optional[np.ndarray] = None
embedder = None  # BGEM3FlagModel
llm: Optional[Llama] = None
LLM_LOCK = Lock()
threads = ThreadStore(APP_ROOT)

# ---------------- User helper & response wrapper -----------------
from flask import make_response
def _get_user_id() -> tuple[str, bool]:
    try:
        uid = request.cookies.get('uid')
    except Exception:
        uid = None
    new = False
    if not uid:
        uid = uuid.uuid4().hex
        new = True
    return uid, new

def _resp(data, status: int = 200):
    uid, new = _get_user_id()
    resp = make_response(jsonify(data), status)
    if new:
        try:
            resp.set_cookie('uid', uid, httponly=True, samesite='Lax')
        except Exception:
            pass
    return resp

# ---------- Conversation Session Manager ----------
class SessionManager:
    """In-memory session log with TTL pruning.

    Stores an ordered history per session id:
    - user prompt
    - executed SQL
    - result metadata (columns, row_count)
    - natural-language explanation
    """
    def __init__(self, ttl_seconds: int = 1800):
        self.ttl = ttl_seconds
        self._store = {}

    def _now(self) -> float:
        return time.time()

    def _prune(self):
        now = self._now()
        keys = [k for k, v in self._store.items() if now - v.get("_last", 0) > self.ttl]
        for k in keys:
            try:
                del self._store[k]
            except Exception:
                pass

    def session(self, sid: str) -> dict:
        if not sid:
            sid = str(uuid.uuid4())
        s = self._store.setdefault(sid, {"history": [], "_last": self._now()})
        s["_last"] = self._now()
        self._prune()
        return s

    def add_entry(self, sid: str, prompt: str, sql: str, columns: list, data: list, explanation: str = None):
        """Append a new transcript item for this session."""
        s = self.session(sid)
        s["history"].append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "prompt": prompt,
            "sql": sql,
            "columns": columns or [],
            "row_count": len(data or []),
            "explanation": explanation,
        })
        s["_last"] = self._now()

    def last(self, sid: str) -> Optional[dict]:
        """Return the most recent transcript item, if any."""
        s = self.session(sid)
        return s["history"][-1] if s["history"] else None

session_mgr = SessionManager(ttl_seconds=1800)

def _get_session_id() -> str:
    """Derive a best-effort session id from headers/cookies/peer.

    Clients should set `X-Session-Id` for reliability across restarts.
    """
    # Prefer header, then cookie, then derived fallback
    sid = request.headers.get("X-Session-Id") or request.cookies.get("asklytics_session")
    if not sid:
        ua = request.headers.get("User-Agent", "")
        sid = f"{request.remote_addr}:{hash(ua)%1000000}"
    return sid

# Optional Redis-backed session manager
class RedisSessionManager(SessionManager):
    """Redis-backed session manager with key TTL eviction.

    Set REDIS_URL to activate. Falls back to the in-memory manager otherwise.
    """
    def __init__(self, url: str, ttl_seconds: int = 1800):
        super().__init__(ttl_seconds)
        self.r = _redis.Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5, decode_responses=True)
        # light ping to validate
        try:
            self.r.ping()
        except Exception:
            raise

    def _key(self, sid: str) -> str:
        return f"asklytics:session:{sid}"

    def session(self, sid: str) -> dict:
        if not sid:
            sid = str(uuid.uuid4())
        key = self._key(sid)
        raw = self.r.get(key)
        if raw:
            s = _json.loads(raw)
        else:
            s = {"history": [], "_last": time.time()}
        s["_last"] = time.time()
        self.r.set(key, _json.dumps(s), ex=self.ttl)
        return s

    def add_entry(self, sid: str, prompt: str, sql: str, columns: list, data: list, explanation: str = None):
        key = self._key(sid)
        s = self.session(sid)
        s["history"].append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "prompt": prompt,
            "sql": sql,
            "columns": columns or [],
            "row_count": len(data or []),
            "explanation": explanation,
        })
        s["_last"] = time.time()
        self.r.set(key, _json.dumps(s), ex=self.ttl)

    def last(self, sid: str) -> Optional[dict]:
        key = self._key(sid)
        raw = self.r.get(key)
        if not raw:
            return None
        s = _json.loads(raw)
        return s.get("history", [])[-1] if s.get("history") else None

# prefer Redis if available
try:
    if _redis and os.getenv("REDIS_URL"):
        session_mgr = RedisSessionManager(os.getenv("REDIS_URL"), ttl_seconds=int(os.getenv("SESSION_TTL", "1800")))
except Exception as _e:
    logger.warning(f"Redis not available for sessions: {_e}")

# ---------- Intent detection / SQL revision ----------
class Intent:
    NEW_QUERY = "NEW_QUERY"
    REFINE_FILTER = "REFINE_FILTER"
    REFINE_ADD_COLUMN = "REFINE_ADD_COLUMN"
    COMPARE = "COMPARE"
    SUMMARIZE = "SUMMARIZE"
    EXPLAIN = "EXPLAIN"

def detect_intent(text: str) -> tuple:
    """Minimal rules to bucket a prompt into coarse intents.

    This is intentionally tiny to keep latency low. You can swap in a small
    classifier later without changing downstream call sites.
    """
    t = (text or "").strip().lower()
    if any(k in t for k in ["summarize", "explain in", "two sentences", "summary"]):
        return (Intent.SUMMARIZE, {})
    if any(k in t for k in ["explain", "how", "why"]):
        return (Intent.EXPLAIN, {})
    if any(k in t for k in ["compare", "yoy", "last year", "previous year"]):
        return (Intent.COMPARE, {})
    if any(k in t for k in ["add column", "add ", "include ", "show "]):
        return (Intent.REFINE_ADD_COLUMN, {"hint": text})
    if any(k in t for k in ["filter", "where", "only", "just", "in "]):
        return (Intent.REFINE_FILTER, {"hint": text})
    return (Intent.NEW_QUERY, {})

def _append_where(sql: str, clause: str) -> str:
    if re.search(r"\bwhere\b", sql, re.IGNORECASE):
        return re.sub(r"(?is)(where)(.*?)(order\s+by|group\s+by|$)", lambda m: f"{m.group(1)} {m.group(2)} AND {clause} {m.group(3)}", sql)
    return re.sub(r"(?is)(order\s+by|group\s+by|$)", lambda m: f" WHERE {clause} {m.group(1)}", sql)

def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())

def _used_tables(sql: str) -> list:
    try:
        return meta._extract_tables_from_sql(sql)
    except Exception:
        return []

def _catalog_selected_columns() -> dict:
    """Return { 'schema.table': {'cols': [orig_names], 'norm': [normalized_names]} } using fallback SQLite first, then store."""
    cat = {}
    try:
        import sqlite3
        db_file = meta._sqlite_path_from_env()
        conn = sqlite3.connect(db_file)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            rows = cur.execute("SELECT a.SchemaName, a.ObjectName, c.ColumnName FROM mm_asset a JOIN mm_column c ON a.AssetId=c.AssetId").fetchall()
            for r in rows:
                key = f"{r['SchemaName']}.{r['ObjectName']}".lower()
                cat.setdefault(key, {"cols": [], "norm": []})
                cat[key]["cols"].append(r["ColumnName"])
                cat[key]["norm"].append(_normalize(r["ColumnName"]))
            return cat
        finally:
            conn.close()
    except Exception:
        pass
    # try SQLAlchemy path
    try:
        if getattr(meta, 'MetaSession', None) and getattr(meta, 'search_assets', None):
            with meta.MetaSession() as s:
                rows = meta.search_assets(s, q="", limit=10000)
                for a in rows or []:
                    detail = meta.get_asset_detail(s, int(a.get("AssetId")))
                    key = (a.get("Key") or "").split(":")[-1].lower()
                    for c in (detail.get("Columns") or []):
                        cat.setdefault(key, {"cols": [], "norm": []})
                        cat[key]["cols"].append(c.get("ColumnName"))
                        cat[key]["norm"].append(_normalize(c.get("ColumnName")))
    except Exception:
        pass
    return cat

def refine_sql(last_sql: str, intent: str, payload: dict) -> Optional[str]:
    """Attempt to transform the previous SQL based on a follow-up intent.

    Supported:
    - REFINE_FILTER: add a WHERE clause based on detected column+value
    - REFINE_ADD_COLUMN: add a visible column to the SELECT list
    (COMPARE stub is present but not implemented here)
    """
    if not last_sql:
        return None
    s = last_sql.strip()
    used = [t.lower() for t in _used_tables(s)]
    catalog = _catalog_selected_columns()
    # build list of available columns in used tables
    used_cols = []
    for t in used:
        if t in catalog:
            used_cols.extend([(t, catalog[t]["cols"][i], catalog[t]["norm"][i]) for i in range(len(catalog[t]["cols"]))])
    if intent == Intent.REFINE_FILTER:
        hint = (payload.get("hint") or "").lower()
        # try parse 'filter <col> = <val>'
        m = re.search(r"filter\s+([a-z0-9_\[\]\.]*)\s*(=|like|contains)?\s*('?\w[^']*'?)?", hint)
        if m and m.group(1) and m.group(3):
            col_hint = _normalize(m.group(1))
            val = m.group(3).strip(" '")
            # find best column match
            for t, orig, norm in used_cols:
                if col_hint in norm or norm in col_hint:
                    clause = f"[{orig}] LIKE '%{val[:64]}%'"
                    return _append_where(s, clause)
        # fallback: choose likely dimension column by keywords
        for kw in ["city", "store", "site", "outlet", "vendor", "customer", "status", "region", "state", "zone"]:
            if kw in hint:
                # value = last token not keyword
                val = re.sub(r".*\b%s\b" % kw, "", hint).strip().strip(".,")
                for t, orig, norm in used_cols:
                    if kw in norm:
                        clause = f"[{orig}] LIKE '%{val[:64]}%'"
                        return _append_where(s, clause)
        return None
    if intent == Intent.REFINE_ADD_COLUMN:
        hint = payload.get("hint") or ""
        m = re.search(r"(?:add|include|show)\s+([a-z0-9_%\[\]\.]*)", hint, flags=re.I)
        cand = (m.group(1) if m else "")
        cand_norm = _normalize(cand)
        pick = None
        for t, orig, norm in used_cols:
            if cand_norm and (cand_norm in norm or norm in cand_norm):
                pick = (t, orig); break
        if not pick and cand_norm:
            # try substring over all
            for t, orig, norm in used_cols:
                if cand_norm[:4] in norm:
                    pick = (t, orig); break
        if pick:
            # Insert column before FROM
            def _ins(mo):
                sel = mo.group(1).strip()
                add = f"[{pick[1]}]"
                if sel.endswith("*"):
                    # already selecting all: keep
                    return f"SELECT {sel} FROM"
                return f"SELECT {sel}, {add} FROM"
            out = re.sub(r"(?is)select\s+(.*?)\s+from", _ins, s, count=1)
            return out
        return None
    if intent == Intent.COMPARE:
        # Naive: try to replace GETDATE() year with year-1 or add a previous year CTE is complex; skip
        return None
    return None

def build_explanation(sql: str) -> str:
    """Create a short provenance string from tables and known relationships."""
    try:
        tables = meta._extract_tables_from_sql(sql)
        rels = meta._collect_relationships()
        used = set(tables)
        edges = []
        for ssch, stab, scol, dsch, dtab, dcol in rels:
            if f"{ssch}.{stab}" in used and f"{dsch}.{dtab}" in used:
                edges.append(f"[{ssch}].[{stab}]  [{dsch}].[{dtab}] ON {scol}={dcol}")
        base = "This insight comes from " + ", ".join(f"[{t.split('.')[0]}].[{t.split('.')[1]}]" for t in tables)
        if edges:
            base += "; joins: " + "; ".join(edges[:3])
        return base
    except Exception:
        return ""

def summarize_rows(columns: list, rows: list) -> Optional[str]:
    """LLM-based two-sentence summary of a small sample of rows."""
    try:
        if not rows or not columns:
            return None
        # Build a compact text for LLM
        sample = rows[: min(30, len(rows))]
        header = ", ".join(columns)
        lines = [", ".join([str(r.get(c)) for c in columns]) for r in sample]
        prompt = (
            "You are a business analyst. Summarize the following table in 2 concise sentences. "
            "Highlight trend, variance, and a plausible driver if visible.\n\n"
            f"Columns: {header}\n" + "\n".join(lines)
        )
        if llm:
            with LLM_LOCK:
                out = llm(prompt, max_tokens=80, temperature=0.2, stop=["\n\n"]).get("choices", [{}])[0].get("text", "").strip()
            return out or None
        return None
    except Exception:
        return None

# Ensure llama.cpp model closes safely before interpreter teardown
def _close_llm_safely():
    global llm
    if llm is None:
        return
    try:
        # Guard against shutdown-order issues inside llama_cpp
        close_fn = getattr(llm, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except TypeError:
                # Happens if llama_cpp internals already nulled; ignore
                pass
            except Exception:
                pass
    finally:
        llm = None

atexit.register(_close_llm_safely)

# ... (ConnectionPool, get_db_connection, initialize_models, load_faiss are unchanged from your last version) ...
class ConnectionPool:
    """Very small fixed-size connection pool for pyodbc.

    Why roll our own here?
    - pyodbc doesn't ship a pool; we only need a handful of long-lived
      connections to reduce handshake latency and improve UX.
    - The implementation is deliberately simple: a Queue plus a few guards.
    """
    def __init__(self, size: int = 5):
        self.size = size; self.connections: "Queue[pyodbc.Connection]" = Queue(maxsize=size); self._initialize_pool()
    def _create_connection(self) -> pyodbc.Connection:
        db = config.get("db"); conn_str = f"DRIVER={{{db['driver']}}};SERVER={db['server']};DATABASE={db['database']};UID={db['uid']};PWD={db['pwd']};TrustServerCertificate=yes;"; return pyodbc.connect(conn_str, timeout=db["timeout"])
    def _initialize_pool(self) -> None:
        created = 0
        for _ in range(self.size):
            try: self.connections.put(self._create_connection(), block=False); created += 1
            except Exception as e: logger.error(f"Initial DB connection failed: {e}"); raise  # Raise error to stop pool creation
        logger.info(f"Connection pool init: {created}/{self.size}")
    def get_connection(self, timeout: int = 5) -> pyodbc.Connection:
        try: return self.connections.get(block=True, timeout=timeout)
        except Empty: logger.warning("Pool empty; creating ad-hoc connection"); return self._create_connection()
    def return_connection(self, conn: pyodbc.Connection) -> None:
        try: self.connections.put(conn, block=False)
        except Exception:
            try: conn.close()
            except Exception: pass
@contextmanager
def get_db_connection() -> Generator[pyodbc.Connection, None, None]:
    """Context-managed access to a pooled pyodbc connection."""
    global connection_pool;
    if not connection_pool: raise ConnectionError("Database connection has not been activated.")
    conn = connection_pool.get_connection()
    try: yield conn
    finally:
        if conn: connection_pool.return_connection(conn)

def initialize_models() -> None:
    """Load the embedding model and the local LLM (llama.cpp).

    - Embeddings: BGE M3 (FlagEmbedding) on CPU/GPU depending on availability
    - LLM: llama.cpp GGUF file if MODEL_PATH is configured
    """
    global embedder, llm
    logger.info("Initializing models...")

    cuda = _cuda_diag()
    logger.info(
        "Torch/CUDA: imported=%s, torch=%s, cuda_avail=%s, cuda_ver=%s, gpus=%s, gpu0=%s",
        cuda["torch_imported"], cuda["torch_version"], cuda["cuda_available"],
        cuda["cuda_version"], cuda["gpu_count"], cuda["gpu_name"],
    )

    # --- Light Embedding model (FlagEmbedding) ---
    try:
        device = "cuda" if cuda["cuda_available"] else "cpu"
        embedder = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True if device == "cuda" else False, device=device)
        logger.info("FlagEmbedding model loaded on device: %s", device)
    except Exception as e:
        logger.critical("Failed to load FlagEmbedding model: %s", e, exc_info=True)

    # --- Llama.cpp model (env-driven with safe fallback) ---
    llm_conf = config.get("llm")
    # Normalize env values (strip quotes/comments)
    def _env_clean(name: str, default: str) -> str:
        raw = os.getenv(name, default)
        try:
            # remove surrounding quotes and inline comments
            raw = raw.strip().strip("\"")
            if "#" in raw:
                raw = raw.split("#", 1)[0].strip()
        except Exception:
            pass
        return raw
    # Pull runtime params with sane defaults
    model_path = _env_clean("MODEL_PATH", llm_conf.get("model_path") or "")
    n_ctx = int(_env_clean("MODEL_CTX", str(llm_conf.get("n_ctx", 4096))) or 4096)
    n_threads = int(_env_clean("MODEL_THREADS", str(llm_conf.get("n_threads", 8))) or 8)
    n_gpu_layers = int(_env_clean("MODEL_GPU_LAYERS", str(llm_conf.get("n_gpu_layers", 0))) or 0)
    n_batch = int(_env_clean("MODEL_BATCH", "512") or 512)

    if not model_path:
        logger.warning("MODEL_PATH not set. Local LLM unavailable.")
        return
    if not llm_conf.get("model_path"):
        logger.warning("MODEL_PATH not set. Local LLM unavailable.")
        return

    try:
        if os.path.exists(model_path):
            logger.info(
                "Loading GGUF with llama.cpp | model=%s | n_ctx=%s | n_threads=%s | n_gpu_layers=%s | n_batch=%s",
                model_path, n_ctx, n_threads, n_gpu_layers, n_batch
            )
            try:
                llm_local = Llama(
                    model_path=model_path,
                    n_ctx=n_ctx,
                    n_threads=n_threads,
                    n_gpu_layers=n_gpu_layers,
                    n_batch=n_batch,
                    verbose=False
                )
                llm = llm_local
                logger.info("llama.cpp: GPU offload %s", "ENABLED" if n_gpu_layers > 0 else "DISABLED")
                logger.info("Local LLM loaded successfully (ctx=%s, batch=%s, threads=%s).", n_ctx, n_batch, n_threads)
            except Exception as e1:
                logger.warning("LLM init failed with configured params, retrying safe defaults: %s", e1)
                # Safe fallback: CPU-only, smaller context/batch
                try:
                    llm_local = Llama(
                        model_path=model_path,
                        n_ctx=min(4096, n_ctx),
                        n_threads=max(2, n_threads // 2),
                        n_gpu_layers=0,
                        n_batch=min(128, n_batch),
                        verbose=False
                    )
                    llm = llm_local
                    logger.info("Local LLM initialized with safe defaults (ctx<=4096, batch<=128, CPU-only).")
                except Exception as e2:
                    logger.critical("Failed to init LLM after fallback: %s", e2, exc_info=True)
                    llm = None
        else:
            logger.error("LLM model not found at %s", model_path)
    except Exception as e:
        logger.critical("Failed to init LLM: %s", e, exc_info=True)


def load_faiss_index_and_strings(reload: bool = False) -> bool:
    """Read FAISS index and companion strings from disk.

    Returns True when both structures are loaded, False otherwise.
    """
    global faiss_index, knowledge_strings
    if faiss_index is not None and not reload: return True
    faiss_cfg = config.get("faiss"); idx_path, str_path = faiss_cfg["index_path"], faiss_cfg["strings_path"]
    if os.path.exists(idx_path) and os.path.exists(str_path):
        try:
            faiss_index = faiss.read_index(idx_path); knowledge_strings = np.load(str_path, allow_pickle=True)
            logger.info(f"FAISS loaded with {faiss_index.ntotal} items"); return True
        except Exception as e:
            logger.error(f"FAISS load error: {e}", exc_info=True); faiss_index, knowledge_strings = None, None; return False
    logger.warning("FAISS files not found; build from /settings"); return False

# ... (Routes and API Endpoints are mostly unchanged, but will now be more reliable) ...
@app.route("/")
def home():
    if not config.is_db_configured() or not load_faiss_index_and_strings(): return redirect(url_for("settings"))
    return render_template("index.html")
@app.route("/settings")
def settings(): return render_template("settings.html")

@app.route("/api/status", methods=["GET"])
def status():
    cu = _cuda_diag()
    return jsonify({
        "database_configured": config.is_db_configured(),
        "faiss_index_loaded": bool(faiss_index and faiss_index.ntotal > 0),
        "llm_loaded": llm is not None,
        "connection_pool_active": connection_pool is not None,
        "inference_mode": config.get_inference_mode(),
        "torch": {"version": cu["torch_version"], "cuda_available": cu["cuda_available"], "cuda_version": cu["cuda_version"], "gpu_name": cu["gpu_name"]},
        "embedder_device": str(getattr(embedder, "_target_device", None)) if embedder else None,
    })


@app.route("/api/db_info", methods=["GET"])
def db_info():
    if config.is_db_configured(): db = config.get("db"); return jsonify({"server": db.get("server"), "database": db.get("database")})
    return jsonify({"server": "N/A", "database": "Not Configured"})
@app.route("/api/settings/db/current", methods=["GET"])
def get_current_db_config():
    db = config.get("db").copy(); db.pop("pwd", None); return jsonify(db), 200
@app.route("/api/settings/db/test", methods=["POST"])
def test_db_connection():
    details = request.get_json(force=True) or {};
    try: conn_str = f"DRIVER={{{details['driver']}}};SERVER={details['server']};DATABASE={details['database']};UID={details['uid']};PWD={details['pwd']};TrustServerCertificate=yes;"; pyodbc.connect(conn_str, timeout=int(details.get("timeout", 5))).close(); return jsonify({"status": "success", "message": "Connection test successful!"})
    except Exception as e: return jsonify({"status": "error", "message": f"Connection test failed: {e}"})
@app.route("/api/settings/db/save", methods=["POST"])
def save_db_connection():
    details = request.get_json(force=True) or {}; required = ["server", "database", "uid", "pwd"]; missing = [k for k in required if not details.get(k)]
    if missing: return jsonify({"status": "error", "message": f"Missing fields: {', '.join(missing)}"}), 400
    config.update_db_config(details)
    def _init_pool_async():
        global connection_pool
        try: connection_pool = ConnectionPool(size=5); logger.info("DB pool initialized (async)")
        except Exception as e: logger.error(f"Pool init failed: {e}", exc_info=True)
    Thread(target=_init_pool_async, daemon=True).start(); return jsonify({"status": "success", "message": f"Configuration saved. Pool starting"}), 200

# --- Table selection APIs ---
@app.route("/api/settings/tables/list", methods=["GET"])
def list_tables():
    """Return available tables and currently selected tables.
    Always returns {tables: [...], selected: [...]} for UI robustness.
    """
    selected = config.get_selected_tables()
    tables = []
    if not config.is_db_configured():
        return jsonify({"tables": tables, "selected": selected})
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            q = "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME;"
            for s, t in cur.execute(q).fetchall():
                tables.append(f"[{s}].[{t}]")
    except Exception as e:
        logger.error("Failed to list tables: %s", e)
        # fallback empty table list but keep selected for display
    return jsonify({"tables": tables, "selected": selected})

@app.route("/api/settings/tables/save", methods=["POST"])
def save_tables():
    payload = request.get_json(force=True) or {}
    tables = payload.get("tables") or []
    if not isinstance(tables, list):
        return jsonify({"status": "error", "message": "Invalid payload."}), 400
    # Normalize values like schema.table or [schema].[table] to [schema].[table]
    norm = []
    for t in tables:
        try:
            s = str(t).strip()
            m = re.match(r"^\[?([^\.\]]+)\]?\.\[?([^\.\]]+)\]?$", s)
            if m:
                norm.append(f"[{m.group(1)}].[{m.group(2)}]")
            else:
                norm.append(s)
        except Exception:
            continue
    config.set_selected_tables(norm)
    return jsonify({"status": "success", "count": len(norm)})

# --- Inference mode APIs ---
@app.get("/api/settings/inference")
def get_inference():
    try:
        return jsonify({"inference": config.get_inference_mode()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Quiet favicon.ico 404s in dev
@app.get("/favicon.ico")
def favicon_blank():
    return ("", 204)

@app.post("/api/settings/inference")
def set_inference():
    try:
        payload = request.get_json(force=True) or {}
        mode = (payload.get("inference") or "").lower()
        config.set_inference_mode(mode)
        return jsonify({"status": "success", "inference": config.get_inference_mode()})
    except ValueError as ve:
        return jsonify({"status": "error", "message": str(ve)}), 400
    except Exception as e:
        logger.error("Failed to save inference mode: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": "Failed to save inference mode."}), 500
# training
@app.route("/api/training/run", methods=["POST"])
def run_training():
    def _run_build_task():
        logger.info("Starting schema indexing task ")
        if not (config.is_db_configured() and embedder): logger.error("Cannot build index: DB not configured or embedder not loaded"); return
        try:
            with get_db_connection() as conn:
                q = "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION;"
                rows = conn.cursor().execute(q).fetchall(); tables = {}
                selected = set(config.get_selected_tables() or [])
                for r in rows:
                    key = f"[{r.TABLE_SCHEMA}].[{r.TABLE_NAME}]"; col = f"[{r.COLUMN_NAME}] {r.DATA_TYPE}"
                    if getattr(r, "CHARACTER_MAXIMUM_LENGTH", None) is not None: col += f"({r.CHARACTER_MAXIMUM_LENGTH})"
                    if selected and key not in selected:
                        continue
                    tables.setdefault(key, []).append(col)
                schema_chunks = [f"Table {t} has columns: {', '.join(cols)}." for t, cols in tables.items()]
            if not schema_chunks: logger.warning("No tables discovered; aborting index build"); return
            logger.info(f"Embedding {len(schema_chunks)} tables ")
    
    # Log device during training/embedding
            try:
                logger.info("Embedding on device: %s", getattr(embedder, "_target_device", "unknown"))
            except Exception:
                pass
            # BGE-M3 returns a dictionary; we only need the dense vectors
            emb_out = embedder.encode(schema_chunks, batch_size=16)
            embs = np.asarray(emb_out["dense_vecs"], dtype="float32")
            index = faiss.IndexFlatL2(embs.shape[1])
            index.add(embs)


            # embs = embedder.encode(schema_chunks, convert_to_numpy=True, show_progress_bar=True); embs = np.asarray(embs, dtype="float32")
            index = faiss.IndexFlatL2(embs.shape[1]); index.add(embs)
            faiss_cfg = config.get("faiss"); faiss.write_index(index, faiss_cfg["index_path"]); np.save(faiss_cfg["strings_path"], np.array(schema_chunks, dtype=object))
            logger.info("Index build complete; reloading in memory"); load_faiss_index_and_strings(reload=True)
        except Exception as e: logger.error(f"Index build failed: {e}", exc_info=True)
    Thread(target=_run_build_task, daemon=True).start()
    return jsonify({"status": "success", "message": "Knowledge build started."}), 202

@app.route("/api/faiss/reload", methods=["POST"])
def reload_faiss():
    if load_faiss_index_and_strings(reload=True): return jsonify({"status": "success", "message": f"Reloaded {faiss_index.ntotal} items."})
    return jsonify({"status": "error", "message": "Reload failed; files missing/corrupt."}), 500

# ... (Streaming functions are unchanged from your last correct version) ...
def _json_sanitize(obj):
    """Recursively convert objects into JSON-serializable forms.
    Handles datetime/date/time, Decimal, numpy scalars/arrays, bytes, and generic iterables.
    Fallback: str(obj).
    """
    try:
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, (datetime, date, dtime)):
            return obj.isoformat()
        if isinstance(obj, decimal.Decimal):
            try:
                return float(obj)
            except Exception:
                return str(obj)
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        if isinstance(obj, dict):
            return {str(k): _json_sanitize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [_json_sanitize(v) for v in obj]
        # Numpy types
        try:
            import numpy as _np  # local import to avoid circular init
            if isinstance(obj, _np.generic):
                return obj.item()
            if isinstance(obj, _np.ndarray):
                return obj.tolist()
        except Exception:
            pass
    except Exception:
        pass
    return str(obj)

def stream_event(event_type: str, data: dict):
    payload = json.dumps({"type": event_type, "data": _json_sanitize(data)})
    return f"data: {payload}\n\n"
def parse_sql_error(e: pyodbc.Error) -> str:
    error_message = str(e); match = re.search(r"\[SQL Server\](.*?)(?:\s*\[|\s*$)", error_message)
    if match: return match.group(1).strip()
    return "An unspecified SQL error occurred."
@app.route("/api/ask/stream", methods=["POST"])
def ask_stream():
    """Local LLM path for SQL generation with SSE streaming.

    Pipeline:
    - (Optional) Try refine+execute based on last SQL and current intent
    - Otherwise, retrieve schema+metadata context and prompt the local LLM
    - Enforce/normalize T-SQL and execute
    - Stream: tokens (optional), sql_complete, result, explanation, summary
    """
    if not (llm and embedder and faiss_index):
        def error_stream(): yield stream_event("error", {"message": "System not fully initialized."})
        return Response(error_stream(), mimetype="text/event-stream")
    data = request.get_json(force=True) or {}; question = (data.get("question") or "").strip(); force_sql = data.get("force_sql")
    def generate_response():
        # Initialize before use so error paths are safe
        full_sql, clean_sql = "", ""
        try:
            # Intent and potential refinement
            sid = _get_session_id()
            last = session_mgr.last(sid)
            intent, payload = detect_intent(question)
            refined_sql = None
            if force_sql:
                pass
            elif last and intent in (Intent.REFINE_FILTER, Intent.REFINE_ADD_COLUMN, Intent.COMPARE):
                refined_sql = refine_sql(last.get("sql"), intent, payload)
            if not force_sql and not refined_sql:
                k = min(config.get("faiss")["retrieval_k"], faiss_index.ntotal or 0)
                q_emb = np.array(embedder.encode([question])["dense_vecs"], dtype="float32")
                # q_emb = embedder.encode([question], convert_to_numpy=True).astype("float32")
                _, I = faiss_index.search(q_emb, k); context = "\n---\n".join(knowledge_strings[i] for i in I[0]);
                combined_context = meta.meta_pre_prompt(question, context, k=5)

            base_prompt = (
                "You are an expert T-SQL (Microsoft SQL Server) query generator.\n"
                "Task: Produce a single valid T-SQL SELECT statement for the question.\n\n"
                "Hard constraints (must follow):\n"
                "- Use only SQL Server T-SQL syntax.\n"
                "- Prefer SELECT TOP (N) instead of LIMIT.\n"
                "- For pagination, use ORDER BY ... OFFSET x ROWS FETCH NEXT y ROWS ONLY.\n"
                "- Use GETDATE(), DATEADD/DATEDIFF/DATEPART, YEAR(), MONTH(), CONVERT/CAST.\n"
                "- Identifiers: [schema].[table], [column]; no double-quotes/backticks.\n"
                "- Concatenation: CONCAT(a,b) or a + b (not ||).\n"
                "- Forbidden: LIMIT, ILIKE, :: casts, DATE_TRUNC, EXTRACT, USING join, RETURNING, JSONB operators.\n\n"
                "Join guidance:\n"
                "- Use the Relationships (FK->PK) section to pick JOIN keys.\n"
                "- When the question spans entities, join tables via the listed FK edges.\n"
                "- Prefer INNER JOIN unless otherwise implied.\n\n"
                f"Schema Context:\n{combined_context}\n\n"
                f"Question:\n{question}\n\n"
                "SQL Server Query:"
            )
            attempts = 2
            violation = None
            clean_sql = None
            for attempt in range(attempts):
                prompt = base_prompt
                if attempt > 0:
                    prompt += (
                        "\n\nNote: The previous output contained non-T-SQL constructs. "
                        "Regenerate strictly valid T-SQL following the constraints."
                    )
                with LLM_LOCK:
                    result = llm(prompt, max_tokens=512, temperature=0.1, stop=["###", "\n\n\n"], stream=False)
                text = result.get("choices", [{}])[0].get("text", "")
                candidate = re.search(r"(?is)SELECT\b.*", text)
                raw_sql = (candidate.group(0) if candidate else text).strip()
                raw_sql = re.sub(r"```.*?```", "", raw_sql, flags=re.DOTALL).strip().rstrip(";")
                try:
                    normalized = enforce_tsql(raw_sql, dialect="tsql", mode="translate")
                    if contains_postgresisms(normalized):
                        violation = "Non-T-SQL constructs detected after normalization."
                        continue
                    clean_sql = normalized
                    violation = None
                    break
                except Exception:
                    violation = "Failed to normalize to valid T-SQL."
                    continue
            if force_sql:
                clean_sql = enforce_tsql(force_sql, dialect="tsql", mode="translate").rstrip(";")
            elif refined_sql:
                clean_sql = enforce_tsql(refined_sql, dialect="tsql", mode="translate").rstrip(";")
            if not force_sql and not refined_sql and not clean_sql:
                raise ValueError(violation or "Generated SQL was not valid T-SQL.")
            # Track final SQL for error reporting
            full_sql = clean_sql
            meta.meta_post_execute(clean_sql)
            yield stream_event("sql_complete", {"query": clean_sql})
            yield stream_event("executing", {"message": "Executing SQL query..."})
            with get_db_connection() as conn:
                # Hybrid validation (rule + semantic + shadow COUNT(*)) before execution
                signals = _run_hybrid_validation(clean_sql, question) or {}
                cur = conn.cursor()
                t0 = time.time()
                cur.execute(clean_sql)
                columns = [d[0] for d in cur.description] if cur.description else []
                data_rows = [dict(zip(columns, r)) for r in cur.fetchall()]
                exec_ms = (time.time() - t0) * 1000.0
            yield stream_event("result", {"columns": columns, "data": data_rows})
            # Explanation & memory
            exp = build_explanation(clean_sql)
            if exp:
                yield stream_event("explanation", {"text": exp})
            session_mgr.add_entry(sid, question, clean_sql, columns, data_rows, exp)
            # Auto-log experience into learning store (if available)
            try:
                if xp is not None and config.get("app").get("auto_log_learning", True):
                    try:
                        used_tables = []
                        try:
                            used_tables = list(set(meta._extract_tables_from_sql(clean_sql)))
                        except Exception:
                            pass
                        import json as _json_mod
                        _xp_id = xp.save_experience(
                            user_prompt=question,
                            generated_sql=clean_sql,
                            validated_sql=clean_sql,
                            schema_context=locals().get("combined_context"),
                            result_signature=None,
                            score=float((signals or {}).get("confidence_score", 1.0)),
                            success=True,
                            feedback=None,
                            provider="local",
                            exec_ms=exec_ms,
                            tables_used=", ".join(used_tables) if used_tables else None,
                            validation_signals=_json_mod.dumps(signals or {}),
                            confidence_score=float((signals or {}).get("confidence_score", 0.0)),
                            confidence_label=str((signals or {}).get("confidence_label", "Low")),
                        )
                        try:
                            yield stream_event("xp_saved", {"xp_id": int(_xp_id)})
                        except Exception:
                            pass
                    except Exception:
                        # Do not disrupt streaming on logging failures
                        pass
            except Exception:
                pass
            # Audit trail (best effort)
            try:
                audit_logger.log_interaction(APP_ROOT, provider="local", prompt=question, sql=clean_sql or "", feedback="", exec_time_ms=int(exec_ms))
                sig = locals().get("signals") or {}
                if sig:
                    audit_logger.log_validation_summary(APP_ROOT, score=float(sig.get("confidence_score", 0.0)), label=str(sig.get("confidence_label", "")), semantic_conf=float(sig.get("semantic_confidence", 0.0)))
            except Exception:
                pass
            # Auto-summarize
            summary = summarize_rows(columns, data_rows)
            if summary:
                yield stream_event("summary", {"text": summary})
            # Relationship-aware suggestions
            try:
                used = set(meta._extract_tables_from_sql(clean_sql))
                rels = meta._collect_relationships()
                suggestions = []
                rel_hints = []
                for ssch, stab, scol, dsch, dtab, dcol in rels:
                    s_full = f"{ssch}.{stab}"; d_full = f"{dsch}.{dtab}"
                    if s_full in used and d_full not in used:
                        suggestions.append(f"[{dsch}].[{dtab}]")
                    if d_full in used and s_full not in used:
                        suggestions.append(f"[{ssch}].[{stab}]")
                    rel_hints.append(f"[{ssch}].[{stab}].[{scol}] -> [{dsch}].[{dtab}].[{dcol}]")
                if suggestions:
                    yield stream_event("related_tables", {"tables": sorted(set(suggestions))})
                if rel_hints:
                    yield stream_event("relationship_hints", {"edges": rel_hints[:20]})
            except Exception:
                pass
            # Normal completion
            yield stream_event("done", {"message": "Stream complete."})
        except GeneratorExit:
            # Client disconnected: stop cleanly without emitting more events
            try:
                logger.info("Client disconnected during /api/ask/stream")
            except Exception:
                pass
            return
        except pyodbc.Error as e:
            logger.error(f"Streaming SQL error: {e}"); friendly_error = parse_sql_error(e)
            yield stream_event("error", {"message": f"SQL Error: {friendly_error}", "full_query": full_sql})
            yield stream_event("done", {"message": "Stream complete."})
        except Exception as e:
            logger.error(f"Streaming general error: {e}", exc_info=True)
            yield stream_event("error", {"message": str(e), "full_query": full_sql})
            yield stream_event("done", {"message": "Stream complete."})
    return Response(stream_with_context(generate_response()), mimetype="text/event-stream")
    

@app.route("/api/gemini_ask/stream", methods=["POST"])
def gemini_ask_stream():
    """Gemini path for SQL generation with SSE streaming.

    Mirrors ask_stream but uses Gemini for generation.
    Also supports refine+execute when `force_sql` is provided by preview.
    """
    gemini_config = config.get("gemini")
    if not gemini_config.get("api_key"):
        def error_stream(): yield stream_event("error", {"message": "GEMINI_API_KEY is not configured."})
        return Response(error_stream(), mimetype="text/event-stream")
    data = request.get_json(force=True) or {}; question = (data.get("question") or "").strip(); force_sql = data.get("force_sql")
    def generate_response():
        full_sql_raw, clean_sql = "", ""
        try:
            # Intent and potential refinement
            sid = _get_session_id()
            last = session_mgr.last(sid)
            intent, payload = detect_intent(question)
            refined_sql = None
            if last and intent in (Intent.REFINE_FILTER, Intent.REFINE_ADD_COLUMN, Intent.COMPARE):
                refined_sql = refine_sql(last.get("sql"), intent, payload)
            if force_sql:
                clean_sql = enforce_tsql(force_sql, dialect="tsql", mode="translate").rstrip(";")
            elif refined_sql:
                clean_sql = enforce_tsql(refined_sql, dialect="tsql", mode="translate").rstrip(";")
            if not (force_sql or refined_sql):
                # Build schema context then combine with metadata context
                k = min(config.get("faiss")["retrieval_k"], faiss_index.ntotal or 0)
                q_emb = np.asarray(embedder.encode([question])["dense_vecs"], dtype="float32")
                _, I = faiss_index.search(q_emb, k)
                schema_context = "\n---\n".join(knowledge_strings[i] for i in I[0])
                combined_context = meta.meta_pre_prompt(question, schema_context, k=5)

                prompt = (
                    "You are an expert T-SQL (SQL Server) query generator. "
                    "Produce a single valid T-SQL SELECT statement for the question.\n\n"
                    "Hard constraints (must follow):\n"
                    "- Use only SQL Server T-SQL syntax.\n"
                    "- Use SELECT TOP (N) instead of LIMIT; for pagination use ORDER BY ... OFFSET x ROWS FETCH NEXT y ROWS ONLY.\n"
                    "- Use GETDATE(), DATEADD/DATEDIFF/DATEPART, YEAR(), MONTH(), CONVERT/CAST.\n"
                    "- Identifiers: [schema].[table], [column]; no double-quotes/backticks.\n"
                    "- Concatenation: CONCAT(a,b) or a + b (not ||).\n"
                    "- Forbidden: LIMIT, ILIKE, ::, DATE_TRUNC, EXTRACT, USING join, RETURNING, JSONB operators.\n\n"
                    "Join guidance:\n"
                    "- Use the Relationships (FK->PK) section to pick JOIN keys.\n"
                    "- When the question spans entities, join tables via the listed FK edges.\n"
                    "- Prefer INNER JOIN unless otherwise implied.\n\n"
                    f"Context (metadata + schema):\n{combined_context}\n\n"
                    f"Question:\n{question}\n\n"
                    "SQL Server Query:"
                )

                api_url = f"{gemini_config['base_url']}/{gemini_config['model']}:streamGenerateContent?key={gemini_config['api_key']}&alt=sse"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                with requests.post(api_url, json=payload, stream=True, timeout=60) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if line and line.decode('utf-8').startswith('data: '):
                            json_data = json.loads(line.decode('utf-8')[6:])
                            token = json_data["candidates"][0]["content"]["parts"][0]["text"]
                            full_sql_raw += token; yield stream_event("token", {"value": token})
                match = re.search(r"```(?:sql\s*)?(.*?)```", full_sql_raw, re.DOTALL)
                clean_sql = match.group(1).strip() if match else full_sql_raw.strip()
                clean_sql = clean_sql.rstrip(";")
                try:
                    clean_sql = enforce_tsql(clean_sql, dialect="tsql", mode="translate")
                    if contains_postgresisms(clean_sql):
                        raise ValueError("Detected non-T-SQL constructs after normalization.")
                except Exception as _:
                    raise ValueError("Generated SQL was not valid T-SQL. Please try again.")
                full_sql_raw = clean_sql  # for error reporting
            meta.meta_post_execute(clean_sql)
            yield stream_event("sql_complete", {"query": clean_sql})
            yield stream_event("executing", {"message": "Executing SQL query..."})
            with get_db_connection() as conn:
                # Hybrid validation prior to execution (COUNT(*) only)
                signals = _run_hybrid_validation(clean_sql, question) or {}
                cur = conn.cursor()
                t0 = time.time()
                cur.execute(clean_sql)
                columns = [d[0] for d in cur.description] if cur.description else []
                data_rows = [dict(zip(columns, r)) for r in cur.fetchall()]
                exec_ms = (time.time() - t0) * 1000.0
            yield stream_event("result", {"columns": columns, "data": data_rows})
            # Explanation & memory
            exp = build_explanation(clean_sql)
            if exp:
                yield stream_event("explanation", {"text": exp})
            session_mgr.add_entry(sid, question, clean_sql, columns, data_rows, exp)
            # Auto-summary
            summary = summarize_rows(columns, data_rows)
            if summary:
                yield stream_event("summary", {"text": summary})
            # Relationship-aware suggestions
            try:
                used = set(meta._extract_tables_from_sql(clean_sql))
                rels = meta._collect_relationships()
                suggestions = []
                rel_hints = []
                for ssch, stab, scol, dsch, dtab, dcol in rels:
                    s_full = f"{ssch}.{stab}"; d_full = f"{dsch}.{dtab}"
                    if s_full in used and d_full not in used:
                        suggestions.append(f"[{dsch}].[{dtab}]")
                    if d_full in used and s_full not in used:
                        suggestions.append(f"[{ssch}].[{stab}]")
                    rel_hints.append(f"[{ssch}].[{stab}].[{scol}] -> [{dsch}].[{dtab}].[{dcol}]")
                if suggestions:
                    yield stream_event("related_tables", {"tables": sorted(set(suggestions))})
                if rel_hints:
                    yield stream_event("relationship_hints", {"edges": rel_hints[:20]})
            except Exception:
                pass
            # Auto-log experience into learning store (if available)
            try:
                if xp is not None and config.get("app").get("auto_log_learning", True):
                    try:
                        used_tables = []
                        try:
                            used_tables = list(set(meta._extract_tables_from_sql(clean_sql)))
                        except Exception:
                            pass
                        import json as _json_mod
                        _xp_id = xp.save_experience(
                            user_prompt=question,
                            generated_sql=clean_sql,
                            validated_sql=clean_sql,
                            schema_context=locals().get("combined_context"),
                            result_signature=None,
                            score=float((signals or {}).get("confidence_score", 1.0)),
                            success=True,
                            feedback=None,
                            provider="gemini",
                            exec_ms=exec_ms,
                            tables_used=", ".join(used_tables) if used_tables else None,
                            validation_signals=_json_mod.dumps(signals or {}),
                            confidence_score=float((signals or {}).get("confidence_score", 0.0)),
                            confidence_label=str((signals or {}).get("confidence_label", "Low")),
                        )
                        try:
                            yield stream_event("xp_saved", {"xp_id": int(_xp_id)})
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception:
                pass
            # Audit trail (best effort)
            try:
                audit_logger.log_interaction(APP_ROOT, provider="gemini", prompt=question, sql=clean_sql or "", feedback="", exec_time_ms=int(exec_ms))
                sig = locals().get("signals") or {}
                if sig:
                    audit_logger.log_validation_summary(APP_ROOT, score=float(sig.get("confidence_score", 0.0)), label=str(sig.get("confidence_label", "")), semantic_conf=float(sig.get("semantic_confidence", 0.0)))
            except Exception:
                pass
            # Normal completion
            yield stream_event("done", {"message": "Stream complete."})
        except GeneratorExit:
            try:
                logger.info("Client disconnected during /api/gemini_ask/stream")
            except Exception:
                pass
            return
        except pyodbc.Error as e:
            logger.error(f"Streaming SQL error: {e}"); friendly_error = parse_sql_error(e)
            yield stream_event("error", {"message": f"SQL Error: {friendly_error}", "full_query": clean_sql or full_sql_raw})
            yield stream_event("done", {"message": "Stream complete."})
        except Exception as e:
            logger.error(f"Streaming Gemini error: {e}", exc_info=True)
            yield stream_event("error", {"message": str(e), "full_query": clean_sql or full_sql_raw})
            yield stream_event("done", {"message": "Stream complete."})
    return Response(stream_with_context(generate_response()), mimetype="text/event-stream")

# DIAGNOSTIC ENDPOINTS

@app.route("/api/diagnostics", methods=["GET"])
def diagnostics():
    """Health and configuration snapshot for quick troubleshooting."""
    fa = _faiss_diag()
    cu = _cuda_diag()
    llm_conf = config.get("llm")
    emb_device = None
    try:
        emb_device = str(getattr(embedder, "_target_device", None))
    except Exception:
        pass
    return jsonify({
        "torch": cu,
        "faiss": fa,
        "embedder_device": emb_device,
        "faiss_index_size": int(faiss_index.ntotal) if faiss_index else 0,
        "llama": {
            "model_path": llm_conf.get("model_path"),
            "n_ctx": llm_conf.get("n_ctx"),
            "n_threads": llm_conf.get("n_threads"),
            "n_gpu_layers": llm_conf.get("n_gpu_layers"),
            "loaded": llm is not None,
        },
    })

# Confidence Metrics API
@app.get("/api/metrics/avg_confidence")
def api_avg_confidence():
    try:
        days = int(request.args.get("days", "30"))
    except Exception:
        days = 30
    if not roi_metrics:
        return jsonify({"avg_confidence": 0.0, "days": days, "note": "metrics_service not available"})
    val = roi_metrics.avg_confidence(days)
    return jsonify({"avg_confidence": float(val), "days": days})


@app.get("/api/metrics/confidence_trend")
def api_confidence_trend():
    try:
        weeks = int(request.args.get("weeks", "8"))
    except Exception:
        weeks = 8
    if not roi_metrics:
        return jsonify({"trend": [], "weeks": weeks, "note": "metrics_service not available"})
    data = roi_metrics.weekly_confidence_trend(weeks)
    return jsonify({"trend": data, "weeks": weeks})


@app.get("/api/metrics/accuracy_kpi")
def api_accuracy_kpi():
    try:
        threshold = float(request.args.get("threshold", "0.8"))
    except Exception:
        threshold = 0.8
    try:
        days = int(request.args.get("days", "30"))
    except Exception:
        days = 30
    if not roi_metrics:
        return jsonify({"kpi": 0.0, "threshold": threshold, "days": days, "note": "metrics_service not available"})
    kpi = roi_metrics.accuracy_kpi_confident(threshold, days)
    return jsonify({"kpi": float(kpi), "threshold": float(threshold), "days": days})

@app.get("/api/roi/feedback_trend")
def api_roi_feedback_trend():
    if not roi_metrics:
        return jsonify({"trend": [], "days": 30})
    try:
        days = int(request.args.get("days", "30"))
    except Exception:
        days = 30
    data = roi_metrics.feedback_trend(days)
    return jsonify({"trend": data, "days": days})

# Feedback API
@app.post("/api/feedback/submit")
def api_feedback_submit():
    if fb_mgr is None or fb_dao is None:
        return jsonify({"error": "feedback subsystem unavailable"}), 503
    data = request.get_json(force=True) or {}
    xp_id = int(data.get("xp_id") or 0)
    verdict = (data.get("verdict") or "").strip().lower()
    comment = (data.get("comment") or "").strip()
    if xp_id <= 0 or verdict not in ("correct", "incorrect"):
        return jsonify({"error": "invalid payload"}), 400
    user_id = request.headers.get("X-User-ID") or "anon"
    confidence = None
    try:
        # Fetch SQL text for hashing + fallback confidence from xp
        import sqlite3, os
        sql_text = None
        db_url = os.getenv("LEARN_DB_URL", "sqlite:///./learning_store.db")
        db_path = db_url.split("sqlite:///")[-1]
        con = sqlite3.connect(db_path)
        try:
            row = con.execute("SELECT generated_sql, confidence_score FROM xp WHERE id=?", (xp_id,)).fetchone()
            if row:
                sql_text = row[0]; confidence = confidence or (row[1] if row[1] is not None else None)
        finally:
            con.close()
        fb_id = fb_mgr.record_feedback(xp_id=xp_id, user_id=user_id, verdict=verdict, comment=comment, confidence=confidence, sql_text=sql_text)
        return jsonify({"status": "recorded", "id": int(fb_id)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/feedback/summary")
def api_feedback_summary():
    if fb_dao is None:
        return jsonify({"total": 0, "correct": 0, "incorrect": 0, "accuracy": 0.0})
    try:
        days = int(request.args.get("days", "30"))
    except Exception:
        days = 30
    return jsonify(fb_dao.summary(days))


@app.get("/api/feedback/list")
def api_feedback_list():
    # Require header X-Role: auditor
    role = request.headers.get("X-Role") or ""
    if role.lower() != "auditor":
        return jsonify({"error": "forbidden"}), 403
    if fb_dao is None:
        return jsonify({"results": []})
    try:
        limit = int(request.args.get("limit", "50"))
    except Exception:
        limit = 50
    return jsonify({"results": fb_dao.list_feedback(limit)})

# ---------- Startup (Simplified and Corrected) ----------
@app.post("/api/ask/preview")
def ask_preview():
    try:
        data = request.get_json(force=True) or {}
        question = (data.get("question") or "").strip()
        sid = _get_session_id()
        last = session_mgr.last(sid)
        intent, payload = detect_intent(question)
        refined_sql = None
        if last and intent in (Intent.REFINE_FILTER, Intent.REFINE_ADD_COLUMN, Intent.COMPARE):
            refined_sql = refine_sql(last.get("sql"), intent, payload)
        return jsonify({
            "intent": intent,
            "will_refine": bool(refined_sql),
            "refined_sql": refined_sql
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.post("/api/summarize")
def summarize_last():
    """Generate a short narrative for the last query using up to 50 rows.

    Robust to missing session/sql and non-SELECT queries; logs exceptions.
    """
    try:
        if not config.is_db_configured():
            return jsonify({"error": "Database is not configured."}), 400

        sid = _get_session_id()
        last = session_mgr.last(sid)
        if not last:
            return jsonify({"error": "No session history."}), 400

        sql = (last.get("sql") or "").strip()
        if not sql:
            return jsonify({"error": "No SQL found in last interaction."}), 400

        # Re-run last SQL with a 50-row cap. Prefer in-place TOP injection
        # that respects DISTINCT; otherwise fall back to wrapping as a subquery.
        def _apply_top(sql_in: str, n: int = 50) -> str:
            s = sql_in.strip().rstrip(';')
            # Already limited with TOP?
            if re.match(r"(?is)^\s*select\s+(?:all\s+|distinct\s+)?top\s*\(", s):
                return s
            # SELECT [ALL|DISTINCT] ...
            if re.match(r"(?is)^\s*select\s+", s):
                def _repl(m):
                    mod = m.group('mod') or ''
                    return f"SELECT {mod}TOP ({n}) "
                s2 = re.sub(r"(?is)^\s*select\s+(?P<mod>(?:all|distinct)\s+)?", _repl, s, count=1)
                return s2
            # Fallback: wrap (may fail if inner query has ORDER BY)
            return f"SELECT TOP ({n}) * FROM ({s}) AS src"

        q = _apply_top(sql, 50)

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(q)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [dict(zip(columns, r)) for r in cur.fetchall()]

        text = summarize_rows(columns, rows) or "No summary available."
        return jsonify({"summary": text}), 200
    except Exception as e:
        try:
            logger.exception("/api/summarize failed: %s", e)
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500

# ---------- Evaluation Dashboard & Metrics ----------
@app.get("/dashboard")
def dashboard_page():
    """Render the evaluation dashboard.

    Returns 404 only when the template is not found; otherwise logs
    details and returns 500 for unexpected errors to aid debugging.
    """
    try:
        return render_template("dashboard.html")
    except Exception as e:
        try:
            from jinja2 import TemplateNotFound
        except Exception:
            TemplateNotFound = type("_TNF", (), {})  # fallback sentinel
        if isinstance(e, TemplateNotFound):
            return "Dashboard template missing.", 404
        logger.error("/dashboard render failed: %s", e, exc_info=True)
        return "Dashboard render error. See server logs.", 500

@app.get("/api/metrics/summary")
def metrics_summary():
    try:
        s = metrics_compute_summary()
        return jsonify({
            "total_queries": s.total_queries,
            "average_accuracy": s.average_accuracy,
            "average_correction_rate": s.average_correction_rate,
            "time_saved_ms_est": s.time_saved_ms_est,
            "last_updated": s.last_updated,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/api/metrics/errors")
def metrics_errors_alias():
    # Alias to learning errors to satisfy dashboard contract
    return api_errors()

@app.get("/api/learn/metrics/rollup")
def api_rollup():
    try:
        if learn_eval is None:
            return jsonify({"error": "learning engine not available"}), 500
        days = int(request.args.get("days", 30))
        roll = learn_eval.rolling_accuracy(days)
        size = learn_eval.size_and_growth()
        roll.update({
            "xp_total": size.get("xp_total", 0),
            "xp_7d": size.get("last_7d", 0),
            "xp_30d": size.get("last_30d", 0),
        })
        return jsonify(roll)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------- Explainability endpoints ----------
@app.post("/api/insight/summarize")
def api_insight_summarize():
    try:
        body = request.get_json(force=True) or {}
        columns = body.get('columns') or []
        rows = body.get('rows') or []
        query = body.get('query')
        # rows may be array of arrays; normalize to list[dict]
        if rows and isinstance(rows[0], list) and columns:
            rows = [dict(zip(columns, r)) for r in rows]
        out = _summarize_result_head(columns, rows, query)
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/insight/provenance")
def api_insight_provenance():
    try:
        body = request.get_json(force=True) or {}
        sql = body.get('sql') or ''
        validator_signals = body.get('validator_signals') or {}
        text = _plain_provenance(sql, validator_signals)
        return jsonify({"provenance": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/insight/confidence")
def api_insight_confidence():
    try:
        body = request.get_json(force=True) or {}
        out = _confidence_score(body)
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/insight/explain")
def api_insight_explain():
    try:
        body = request.get_json(force=True) or {}
        columns = body.get('columns') or []
        rows = body.get('rows') or []
        if rows and isinstance(rows[0], list) and columns:
            rows = [dict(zip(columns, r)) for r in rows]
        query = body.get('query')
        sql = body.get('sql') or ''
        signals = body.get('signals') or {}
        summary = _summarize_result_head(columns, rows, query)
        provenance = _plain_provenance(sql, signals.get('validator'))
        confidence = _confidence_score({
            'validator': signals.get('validator') or {},
            'execution': signals.get('execution') or {},
            'retrieval': signals.get('retrieval') or {},
        })
        return jsonify({
            'summary': summary.get('summary', ''),
            'bullets': summary.get('bullets', []),
            'provenance': provenance,
            'confidence': confidence,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.get("/api/learn/metrics/errors")
def api_errors():
    try:
        if learn_eval is None:
            return jsonify({"error": "learning engine not available"}), 500
        days = int(request.args.get("days", 30))
        return jsonify(learn_eval.error_buckets(days))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/api/learn/metrics/joins")
def api_joins():
    try:
        if learn_eval is None:
            return jsonify({"error": "learning engine not available"}), 500
        days = int(request.args.get("days", 30))
        return jsonify(learn_eval.by_table_join(days))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/api/learn/metrics/top")
def api_top():
    try:
        if learn_eval is None:
            return jsonify({"error": "learning engine not available"}), 500
        days = int(request.args.get("days", 30))
        k = int(request.args.get("k", 20))
        return jsonify(learn_eval.top_queries(days, k))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/learn/regression/run")
def api_regression_run():
    try:
        body = request.get_json(silent=True) or {}
        suite = (body.get("suite") or "default").strip()
        tests = body.get("tests")
        result = learn_run_suite(suite_name=suite, tests=tests)
        try:
            path = persist_regression_result(result, APP_ROOT)
            result["_persisted_to"] = str(path)
        except Exception:
            pass
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Learning settings and controls
@app.get("/api/settings/learning")
def get_learning_settings():
    try:
        return jsonify({
            "auto_log_learning": config.get_auto_log_learning()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/settings/learning")
def set_learning_settings():
    try:
        payload = request.get_json(force=True) or {}
        auto_log = bool(payload.get("auto_log_learning", True))
        config.set_auto_log_learning(auto_log)
        return jsonify({"status": "success", "auto_log_learning": config.get_auto_log_learning()})
    except Exception as e:
        logger.error("Failed to save learning settings: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": "Failed to save learning settings."}), 500

@app.post("/api/learn/reindex")
def api_learn_reindex():
    try:
        if learn_reindex is None:
            return jsonify({"status": "error", "message": "learning engine not available"}), 500
        def _run():
            try:
                learn_reindex()
                logger.info("Learning index rebuild completed")
            except Exception as e:
                logger.error("Learning index rebuild failed: %s", e, exc_info=True)
        Thread(target=_run, daemon=True).start()
        return jsonify({"status": "accepted", "message": "Learning index rebuild started."}), 202
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Aliased regression route for dashboard contract
@app.post("/api/regression/run")
def api_regression_run_alias():
    return api_regression_run()

# Simple learning health for footer
@app.get("/api/learn/health")
def learn_health():
    try:
        s = metrics_compute_summary()
        return jsonify({
            "examples": s.total_queries,
            "accuracy": s.average_accuracy,
            "last_updated": s.last_updated,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Audit export
@app.get("/api/audit/export")
def audit_export():
    try:
        out_path = APP_ROOT / "data" / "audit_export.csv"
        p = audit_logger.export_last_30_days_csv(APP_ROOT, out_path)
        return send_file(str(p), mimetype="text/csv", as_attachment=True, download_name="audit_last30.csv")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Learning settings - auto summarize toggle
@app.get("/api/settings/auto_summarize")
def get_auto_summarize():
    try:
        return jsonify({"auto_summarize": config.get_auto_summarize()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/settings/auto_summarize")
def set_auto_summarize():
    try:
        body = request.get_json(force=True) or {}
        flag = bool(body.get("auto_summarize", False))
        config.set_auto_summarize(flag)
        return jsonify({"status": "success", "auto_summarize": config.get_auto_summarize()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ---------------- Chat threads (simple JSON-backed) -----------------
@app.get("/api/threads")
def api_threads_list():
    try:
        uid, _ = _get_user_id()
        lim = int(request.args.get("limit", 10))
        return _resp({"threads": threads.list(user_id=uid, limit=lim)})
    except Exception as e:
        return _resp({"error": str(e)}, 500)

@app.post("/api/threads")
def api_threads_create():
    try:
        uid, _ = _get_user_id()
        body = request.get_json(silent=True) or {}
        title = (body.get("title") or "New Chat").strip()
        # enforce limit
        limit = config.get_chat_limit()
        cur = len(threads.list(user_id=uid, limit=9999))
        if cur >= limit:
            return _resp({"error": "limit_reached"}, 403)
        t = threads.create(uid, title)
        return _resp(t, 201)
    except Exception as e:
        return _resp({"error": str(e)}, 500)

@app.get("/api/threads/<tid>")
def api_threads_get(tid: str):
    try:
        t = threads.get(tid)
        if not t:
            return _resp({"error": "not found"}, 404)
        return _resp(t)
    except Exception as e:
        return _resp({"error": str(e)}, 500)

@app.post("/api/threads/<tid>/rename")
def api_threads_rename(tid: str):
    try:
        body = request.get_json(silent=True) or {}
        title = (body.get("title") or "").strip()
        if not title:
            return _resp({"error": "title required"}, 400)
        ok = threads.rename(tid, title)
        return _resp({"ok": ok}) if ok else _resp({"error": "not found"}, 404)
    except Exception as e:
        return _resp({"error": str(e)}, 500)

@app.post("/api/threads/<tid>/messages")
def api_threads_add_msg(tid: str):
    try:
        body = request.get_json(force=True) or {}
        msg_type = (body.get("type") or "").strip()
        content = (body.get("content") or "").strip()
        if msg_type not in ("user", "bot", "bot-error"):
            return _resp({"error": "invalid type"}, 400)
        ok = threads.add_message(tid, msg_type, content)
        return _resp({"ok": ok}) if ok else _resp({"error": "not found"}, 404)
    except Exception as e:
        return _resp({"error": str(e)}, 500)

@app.delete("/api/threads/<tid>")
def api_threads_delete(tid: str):
    try:
        ok = threads.delete(tid)
        return _resp({"ok": ok}) if ok else _resp({"error": "not found"}, 404)
    except Exception as e:
        return _resp({"error": str(e)}, 500)

@app.post("/api/threads/<tid>/state")
def api_threads_set_state(tid: str):
    try:
        body = request.get_json(force=True) or {}
        ok = threads.set_state(tid, body)
        return _resp({"ok": ok}) if ok else _resp({"error": "not found"}, 404)
    except Exception as e:
        return _resp({"error": str(e)}, 500)

# Chat limit config
@app.get("/api/config/chat_limit")
def get_chat_limit():
    try:
        from flask import make_response
        data = {"chat_session_limit": config.get_chat_limit()}
        resp = make_response(jsonify(data), 200)
        return resp
    except Exception as e:
        from flask import make_response
        return make_response(jsonify({"error": str(e)}), 500)

@app.post("/api/config/chat_limit")
def set_chat_limit():
    try:
        body = request.get_json(force=True) or {}
        n = int(body.get('chat_session_limit', 5))
        config.set_chat_limit(n)
        from flask import make_response
        data = {"status": "success", "chat_session_limit": config.get_chat_limit()}
        return make_response(jsonify(data), 200)
    except Exception as e:
        from flask import make_response
        return make_response(jsonify({"status": "error", "message": str(e)}), 500)

# Feedback review UI and routes (best-effort wrappers)
@app.get("/review")
def review_page():
    try:
        return render_template("review.html")
    except Exception:
        return "Review template missing.", 404

@app.get("/api/review/pending")
def review_pending():
    try:
        if xp is None:
            # Return empty list instead of 501 so UI degrades gracefully
            return jsonify({"results": []})
        # Fallback contract: xp.list_pending() returns list of dicts with id and fields
        if hasattr(xp, "list_pending"):
            rows = xp.list_pending()
        elif hasattr(xp, "list_feedback_pending"):
            rows = xp.list_feedback_pending()
        else:
            # Not implemented in this build — return empty list
            rows = []
        return jsonify({"results": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/review/approve")
def review_approve():
    try:
        if xp is None:
            return jsonify({"status": "ok"})
        body = request.get_json(force=True) or {}
        rid = body.get("id")
        if not rid:
            return jsonify({"error": "id required"}), 400
        if hasattr(xp, "set_feedback_approved"):
            xp.set_feedback_approved(rid, True)
        elif hasattr(xp, "approve_feedback"):
            xp.approve_feedback(rid)
        else:
            return jsonify({"status": "ok"})
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/review/reject")
def review_reject():
    try:
        if xp is None:
            return jsonify({"status": "ok"})
        body = request.get_json(force=True) or {}
        rid = body.get("id")
        if not rid:
            return jsonify({"error": "id required"}), 400
        if hasattr(xp, "set_feedback_approved"):
            xp.set_feedback_approved(rid, False)
        elif hasattr(xp, "reject_feedback"):
            xp.reject_feedback(rid)
        else:
            return jsonify({"status": "ok"})
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    is_production = config.get("app")["env"] == "production"

    config.load_from_file()
    initialize_models()

    if config.is_db_configured():
        logger.info("Persistent config found. Activating database connection pool...")
        try:
            connection_pool = ConnectionPool()
            load_faiss_index_and_strings()
        except Exception as e:
            logger.error(f"Failed to activate connection pool on startup: {e}")
            logger.warning("DB features may fail until credentials are re-saved in Settings.")

    # >>> Initialize the metadata patch BEFORE serving <<<
    meta = AppMetaPatch(app, logger, embedder, get_db_connection, config).init()

    host = "0.0.0.0"; port = 5000
    if is_production:
        logger.info(f"Starting PRODUCTION server on http://{host}:{port}")
        serve(app, host=host, port=port, threads=16)
    else:
        logger.info(f"Starting DEVELOPMENT server on http://{host}:{port} (debug=True)")
        app.run(host=host, port=port, debug=True)

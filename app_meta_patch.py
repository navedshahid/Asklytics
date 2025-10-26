# app_meta_patch.py
# Glue code to integrate the SQLite metadata engine into your existing Flask app.
# - Registers metadata blueprint
# - Starts orchestrator (dynamic updates -> re-embed changed assets)
# - Maintains a separate FAISS index for metadata paragraphs
# - Provides 3 hooks you call from ask_stream/gemini_ask_stream:
#     meta.meta_pre_prompt(question, schema_context) -> combined_context
#     meta.meta_post_execute(clean_sql)              -> logs lineage
#     (plus a /api/metadata/harvest endpoint)

from __future__ import annotations
import os, re, json, typing as T
from flask import Blueprint, jsonify, request

# (removed legacy inline blueprint to avoid confusion)  

# ---------- Optional FAISS ----------
try:
    import numpy as np
except Exception:
    np = None

try:
    import faiss  # faiss-cpu or faiss-gpu
except Exception:
    faiss = None


class AppMetaPatch:
    """Glue between your Flask app and the metadata subsystem.

    Responsibilities (high-level):
    - Register REST endpoints (search/detail/bulk_upsert/harvest/health)
    - Initialize the metadata DB and a small orchestrator for re-embedding
    - Maintain a separate FAISS index for metadata paragraphs
    - Provide prompt-time hooks (meta_pre_prompt/meta_post_execute)
    - Offer fallbacks when SQLAlchemy is unavailable (pure sqlite3)
    """
    def __init__(self, app, logger, embedder, get_db_connection, config):
        """
        app:      your Flask app
        logger:   your logger (e.g., logger = logging.getLogger("GenDS"))
        embedder: FlagEmbedding BGE-M3 instance or None
        get_db_connection: your contextmanager that yields pyodbc connection
        config:   your ConfigManager (for is_db_configured())
        """
        self.app = app
        self.logger = logger
        self.embedder = embedder
        self.get_db_connection = get_db_connection
        self.config = config

        # Imports from the metadata engine (soft-required)
        self._routes_loaded = False
        self._store_loaded = False
        self._orch_loaded = False

        try:
            from metadata_routes import bp as metadata_bp
            self.metadata_bp = metadata_bp
            self._routes_loaded = True
        except Exception as e:
            self.metadata_bp = None
            self.logger.warning(f"[meta] metadata_routes not available: {e}")

        try:
            from metadata_store import (
                SessionLocal as MetaSession,
                init_db as meta_init_db,
                get_asset_detail, publish_event, upsert_asset, upsert_columns,
                search_assets, Asset
            )
            self.MetaSession = MetaSession
            self.meta_init_db = meta_init_db
            self.get_asset_detail = get_asset_detail
            self.publish_event = publish_event
            self.upsert_asset = upsert_asset
            self.upsert_columns = upsert_columns
            self.search_assets = search_assets
            self.Asset = Asset
            self._store_loaded = True
        except Exception as e:
            self.MetaSession = None
            self.meta_init_db = None
            self.get_asset_detail = None
            self.publish_event = None
            self.upsert_asset = None
            self.upsert_columns = None
            self.search_assets = None
            self.logger.warning(f"[meta] metadata_store not available: {e}")

        try:
            from orchestrator import Orchestrator
            self.Orchestrator = Orchestrator
            self._orch_loaded = True
        except Exception as e:
            self.Orchestrator = None
            self.logger.warning(f"[meta] orchestrator not available: {e}")

        # metadata FAISS (separate from your schema index)
        self.META_DIM = int(os.getenv("META_EMBED_DIM", "1024"))
        self.meta_faiss_index = None  # faiss.IndexIDMap2 over IndexFlatL2

    # ---------- Relationship extraction ----------
    def _collect_relationships(self) -> T.List[T.Tuple[str,str,str,str,str,str]]:
        rels: T.List[T.Tuple[str,str,str,str,str,str]] = []
        sel = self._selected_table_set()
        if not sel:
            return rels
        fk_pat = re.compile(r"FK->([\w]+)\.([\w]+)\(([\w]+)\)")

        if self._store_loaded and self.MetaSession and self.get_asset_detail:
            try:
                with self.MetaSession() as s:
                    for schema, table in sel:
                        try:
                            # find asset by exact schema.table
                            q = table
                            rows = self.search_assets(s, q=q, limit=5) if callable(getattr(self, 'search_assets', None)) else []
                            asset_id = None
                            for r in rows or []:
                                key = r.get('Key') or ''
                                # Key like Source:Schema.Table
                                if f".{table}" in key and f":{schema}." in key:
                                    asset_id = r.get('AssetId'); break
                            if not asset_id:
                                continue
                            detail = self.get_asset_detail(s, int(asset_id)) or {}
                            for c in (detail.get('Columns') or []):
                                desc = c.get('Description') or ''
                                m = fk_pat.search(desc)
                                if m:
                                    dst_schema, dst_table, dst_col = m.group(1), m.group(2), m.group(3)
                                    rels.append((schema, table, c.get('ColumnName'), dst_schema, dst_table, dst_col))
                        except Exception:
                            continue
            except Exception:
                pass
            return rels

        # Fallback sqlite path
        try:
            import sqlite3
            db_file = self._sqlite_path_from_env()
            conn = sqlite3.connect(db_file)
            try:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                for schema, table in sel:
                    a = cur.execute(
                        "SELECT AssetId FROM mm_asset WHERE lower(ifnull(SchemaName,''))=? AND lower(ObjectName)=?",
                        (schema, table)
                    ).fetchone()
                    if not a:
                        continue
                    cols = cur.execute(
                        "SELECT ColumnName, Description FROM mm_column WHERE AssetId=?",
                        (a['AssetId'],)
                    ).fetchall()
                    for c in cols:
                        desc = c['Description'] or ''
                        m = fk_pat.search(desc)
                        if m:
                            rels.append((schema, table, c['ColumnName'], m.group(1), m.group(2), m.group(3)))
            finally:
                conn.close()
        except Exception:
            pass
        return rels

    def _relationships_context(self) -> str:
        rels = self._collect_relationships()
        if not rels:
            return ""
        lines = ["Relationships (FK -> PK):"]
        for ssch, stab, scol, dsch, dtab, dcol in rels[:50]:
            lines.append(f"- [{ssch}].[{stab}].[{scol}] -> [{dsch}].[{dtab}].[{dcol}]")
        return "\n".join(lines)

    # ---------- Helpers: selection + sqlite fallback ----------
    def _selected_table_set(self) -> T.Set[T.Tuple[str, str]]:
        try:
            raw = self.config.get_selected_tables() if hasattr(self.config, "get_selected_tables") else []
        except Exception:
            raw = []
        out: T.Set[T.Tuple[str, str]] = set()
        for s in raw or []:
            try:
                ss = str(s).strip()
                # normalize [schema].[table] or schema.table -> (schema_lower, table_lower)
                m = re.match(r"^\[?([^\.\]]+)\]?\.\[?([^\.\]]+)\]?$", ss)
                if m:
                    out.add((m.group(1).strip().lower(), m.group(2).strip().lower()))
                elif "." in ss:
                    p = ss.split(".", 1); out.add((p[0].strip("[] ").lower(), p[1].strip("[] ").lower()))
            except Exception:
                continue
        return out

    def _sqlite_path_from_env(self) -> str:
        db_url = os.getenv("META_DB_URL", "sqlite:///./metadata.db")
        if db_url.startswith("sqlite"):
            return db_url.split("sqlite:///")[-1]
        return "./metadata.db"

    def _fallback_sqlite_prepare(self, conn):
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mm_asset (
              AssetId INTEGER PRIMARY KEY AUTOINCREMENT,
              Kind TEXT NOT NULL,
              Source TEXT NOT NULL,
              SchemaName TEXT,
              ObjectName TEXT NOT NULL,
              DisplayName TEXT,
              Description TEXT,
              OwnerEmail TEXT,
              Sensitivity TEXT DEFAULT 'Internal' NOT NULL,
              TagsJson TEXT,
              Version INTEGER DEFAULT 1 NOT NULL,
              IsActive INTEGER DEFAULT 1 NOT NULL,
              CreatedAt TEXT,
              UpdatedAt TEXT,
              UNIQUE(Source, SchemaName, ObjectName)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mm_column (
              ColumnId INTEGER PRIMARY KEY AUTOINCREMENT,
              AssetId INTEGER NOT NULL,
              OrdinalPos INTEGER NOT NULL,
              ColumnName TEXT NOT NULL,
              DataType TEXT NOT NULL,
              MaxLength INTEGER,
              IsNullable INTEGER NOT NULL,
              Description TEXT,
              IsKey INTEGER NOT NULL DEFAULT 0,
              IsPII INTEGER NOT NULL DEFAULT 0,
              ProfileRowCnt INTEGER,
              ProfileNullPct REAL,
              ProfileMin TEXT,
              ProfileMax TEXT,
              UpdatedAt TEXT,
              FOREIGN KEY(AssetId) REFERENCES mm_asset(AssetId) ON DELETE CASCADE
            );
            """
        )
        # Migrate existing DBs missing newer columns
        try:
            cols = {r[1] for r in cur.execute("PRAGMA table_info('mm_column')").fetchall()}
            if 'IsKey' not in cols:
                cur.execute("ALTER TABLE mm_column ADD COLUMN IsKey INTEGER NOT NULL DEFAULT 0")
            if 'IsPII' not in cols:
                cur.execute("ALTER TABLE mm_column ADD COLUMN IsPII INTEGER NOT NULL DEFAULT 0")
            if 'ProfileRowCnt' not in cols:
                cur.execute("ALTER TABLE mm_column ADD COLUMN ProfileRowCnt INTEGER")
            if 'ProfileNullPct' not in cols:
                cur.execute("ALTER TABLE mm_column ADD COLUMN ProfileNullPct REAL")
            if 'ProfileMin' not in cols:
                cur.execute("ALTER TABLE mm_column ADD COLUMN ProfileMin TEXT")
            if 'ProfileMax' not in cols:
                cur.execute("ALTER TABLE mm_column ADD COLUMN ProfileMax TEXT")
        except Exception:
            pass
        conn.commit()

    def _fallback_upsert_asset(self, conn, asset: dict) -> int:
        from datetime import datetime as _dt
        now = _dt.utcnow().isoformat(timespec="seconds")
        cur = conn.cursor()
        cur.execute(
            "SELECT AssetId, Version FROM mm_asset WHERE Source=? AND ifnull(SchemaName,'')=ifnull(?, '') AND ObjectName=?",
            (asset["Source"], asset.get("SchemaName"), asset["ObjectName"]))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                """
                INSERT INTO mm_asset(Kind, Source, SchemaName, ObjectName, DisplayName, Description, OwnerEmail, Sensitivity, TagsJson, Version, IsActive, CreatedAt, UpdatedAt)
                VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)
                """,
                (
                    asset.get("Kind", "Table"), asset["Source"], asset.get("SchemaName"), asset["ObjectName"],
                    asset.get("DisplayName") or asset["ObjectName"], asset.get("Description"), asset.get("OwnerEmail"),
                    asset.get("Sensitivity") or "Internal", json.dumps(asset.get("TagsJson") or []), 1, now, now,
                ),
            )
            conn.commit()
            return cur.lastrowid
        else:
            asset_id, ver = row
            cur.execute(
                """
                UPDATE mm_asset SET Kind=?, DisplayName=?, Description=?, OwnerEmail=?, Sensitivity=?, TagsJson=?, Version=?, UpdatedAt=?
                WHERE AssetId=?
                """,
                (
                    asset.get("Kind", "Table"), asset.get("DisplayName") or asset["ObjectName"], asset.get("Description"),
                    asset.get("OwnerEmail"), asset.get("Sensitivity") or "Internal", json.dumps(asset.get("TagsJson") or []), int(ver or 1) + 1, now, asset_id,
                ),
            )
            conn.commit()
            return asset_id

    def _fallback_upsert_columns(self, conn, asset_id: int, columns: T.List[dict]):
        from datetime import datetime as _dt
        now = _dt.utcnow().isoformat(timespec="seconds")
        cur = conn.cursor()
        cur.execute("DELETE FROM mm_column WHERE AssetId=?", (asset_id,))
        for c in columns or []:
            # Insert with optional flags; columns not listed will use defaults
            cur.execute(
                """
                INSERT INTO mm_column(
                    AssetId, OrdinalPos, ColumnName, DataType, MaxLength, IsNullable, Description,
                    IsKey, IsPII,
                    UpdatedAt
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    asset_id,
                    int(c.get("OrdinalPos", 0)),
                    c.get("ColumnName"),
                    c.get("DataType"),
                    c.get("MaxLength"),
                    int(c.get("IsNullable", 0)),
                    c.get("Description"),
                    1 if c.get("IsKey") else 0,
                    1 if c.get("IsPII") else 0,
                    now,
                ),
            )
        conn.commit()

    # ---------- Public entrypoint ----------
    def init(self) -> "AppMetaPatch":
        """Initialize the metadata integration.

        - Always registers the harvest/health endpoints so the UI never 404s
        - If SQLAlchemy is available, registers the richer routes and spins
          the orchestrator for dynamic re-embedding
        - Prepares the FAISS index for metadata text
        """
        # Always register the lightweight harvest endpoint so clients don't 404
        try:
            self._register_harvest_endpoint()
        except Exception as e:
            self.logger.warning(f"[meta] failed to register harvest endpoint: {e}")

        if not self._store_loaded:
            self.logger.warning("[meta] metadata_store missing; skipping full metadata engine init.")
            return self

        # 1) DB init (WAL pragmas for SQLite etc.)
        try:
            self.meta_init_db()
        except Exception as e:
            self.logger.error(f"[meta] init_db failed: {e}")

        # 2) Register the metadata blueprint (search, detail, bulk_upsert, events)
        if self._routes_loaded and self.metadata_bp:
            self.app.register_blueprint(self.metadata_bp)
            self.logger.info("[meta] Registered /api/metadata/* endpoints.")

        # 3) (Already registered above) HARVEST endpoint

        # 4) Initialize metadata FAISS index
        self._init_meta_faiss()

        # 5) Start orchestrator (dynamic updates -> re-embed)
        if self._orch_loaded and self.Orchestrator:
            orch = self.Orchestrator(on_reembed=self._reembed_metadata_asset, poll_sec=2)
            orch.start()
            self.logger.info("[meta] Orchestrator started.")
        else:
            self.logger.warning("[meta] Orchestrator not available; dynamic updates disabled.")

        return self

    # ---------- Hooks you call at question time ----------
    def meta_pre_prompt(self, question: str, schema_context: str, k: int = 5) -> str:
        """Return extra context to stitch into your LLM prompt.

        We blend three sources (when available):
        - FAISS-ranked metadata paragraphs (asset summaries)
        - A compact relationships section (FK->PK edges)
        - The existing schema_context (from your main retriever)
        """
        meta_ctx = self._retrieve_metadata_context(question, k=k)
        rel_ctx = self._relationships_context()
        parts = []
        if meta_ctx:
            parts.append(meta_ctx)
        if rel_ctx:
            parts.append(rel_ctx)
        if schema_context:
            parts.append(schema_context)
        return ("\n\n".join(parts)).strip() or schema_context

    def meta_post_execute(self, clean_sql: str) -> None:
        """Log read lineage when a query is executed successfully.

        We emit simple events per table used (best-effort extraction) so other
        components (e.g., orchestrator) can react.
        """
        if not self._store_loaded:
            return
        try:
            tables = self._extract_tables_from_sql(clean_sql or "")
            if not tables:
                return
            with self.MetaSession() as ms:
                for t in tables:
                    schema, name = t.split(".", 1) if "." in t else ("dbo", t)
                    asset_id = self.upsert_asset(ms, {
                        "Kind": "Table", "Source": "SqlServer:D365",
                        "SchemaName": schema, "ObjectName": name,
                        "DisplayName": name, "Sensitivity": "Internal",
                        "TagsJson": ["agent_used"]
                    })
                    self.publish_event(ms, "lineage.upsert", {"asset_id": asset_id},
                                       {"AssetId": asset_id, "Action": "read"})
                ms.commit()
        except Exception as e:
            self.logger.warning(f"[meta] post_execute lineage failed: {e}")

    # ---------- Internal: Harvest ----------
    def _register_harvest_endpoint(self):
        """Register lightweight endpoints we always want present.

        Includes:
        - POST /api/metadata/harvest   (full or fallback harvest)
        - GET  /api/metadata/health    (wiring diagnostics)
        - GET  /api/metadata/assets*   (fallback read paths, only when needed)
        """
        bp = Blueprint("meta_patch", __name__)

        @bp.route("/api/metadata/harvest", methods=["POST"])
        def harvest_metadata_from_sqlserver():
            body = request.get_json(silent=True) or {}
            scope = set((body.get("scope") or ["tables","columns","foreign_keys","views","descriptions","row_counts"]))
            source_name = body.get("source") or "SqlServer:D365"
            if not self.config.is_db_configured():
                return jsonify({"status": "error", "message": "DB not configured"}), 400
            if not self._store_loaded:
                # Fallback: upsert selected tables using builtin sqlite3 store
                try:
                    import sqlite3
                    sel = self._selected_table_set()
                    with self.get_db_connection() as conn:
                        cur = conn.cursor()
                        # tables/views
                        tbls = cur.execute(
                            """
                            SELECT t.TABLE_SCHEMA, t.TABLE_NAME, t.TABLE_TYPE
                            FROM INFORMATION_SCHEMA.TABLES t
                            ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME
                            """
                        ).fetchall()
                        # columns
                        cols = cur.execute(
                            """
                            SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.ORDINAL_POSITION,
                                   c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH, c.IS_NULLABLE
                            FROM INFORMATION_SCHEMA.COLUMNS c
                            ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
                            """
                        ).fetchall()
                        # extended properties (descriptions)
                        xdesc = {}
                        if "descriptions" in scope:
                            try:
                                xp = cur.execute(
                                    """
                                    SELECT s.name AS SchemaName, t.name AS TableName, c.name AS ColumnName, ep.value AS Description
                                    FROM sys.extended_properties ep
                                    JOIN sys.tables t ON ep.major_id = t.object_id
                                    JOIN sys.schemas s ON t.schema_id = s.schema_id
                                    LEFT JOIN sys.columns c ON c.object_id = t.object_id AND ep.minor_id = c.column_id
                                    WHERE ep.name = 'MS_Description';
                                    """
                                ).fetchall()
                                for r in xp:
                                    key = (r.SchemaName, r.TableName, r.ColumnName or "")
                                    xdesc[key] = r.Description
                            except Exception:
                                xdesc = {}
                        # primary keys
                        pk = {}
                        if "foreign_keys" in scope or "columns" in scope:
                            try:
                                pk_rows = cur.execute(
                                    """
                                    SELECT tc.TABLE_SCHEMA, tc.TABLE_NAME, kcu.COLUMN_NAME
                                    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                                    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                                    WHERE tc.CONSTRAINT_TYPE='PRIMARY KEY'
                                    """
                                ).fetchall()
                                for r in pk_rows:
                                    pk.setdefault((r.TABLE_SCHEMA, r.TABLE_NAME), set()).add(r.COLUMN_NAME)
                            except Exception:
                                pk = {}
                        # foreign keys
                        fk = {}
                        if "foreign_keys" in scope:
                            try:
                                fk_rows = cur.execute(
                                    """
                                    SELECT sch1.name AS SchemaName, tab1.name AS TableName, col1.name AS ColumnName,
                                           sch2.name AS RefSchemaName, tab2.name AS RefTableName, col2.name AS RefColumnName
                                    FROM sys.foreign_key_columns fkc
                                    JOIN sys.tables tab1 ON tab1.object_id = fkc.parent_object_id
                                    JOIN sys.schemas sch1 ON sch1.schema_id = tab1.schema_id
                                    JOIN sys.columns col1 ON col1.column_id = fkc.parent_column_id AND col1.object_id = tab1.object_id
                                    JOIN sys.tables tab2 ON tab2.object_id = fkc.referenced_object_id
                                    JOIN sys.schemas sch2 ON sch2.schema_id = tab2.schema_id
                                    JOIN sys.columns col2 ON col2.column_id = fkc.referenced_column_id AND col2.object_id = tab2.object_id
                                    """
                                ).fetchall()
                                for r in fk_rows:
                                    fk[(r.SchemaName, r.TableName, r.ColumnName)] = (r.RefSchemaName, r.RefTableName, r.RefColumnName)
                            except Exception:
                                fk = {}
                        # last modified per table
                        last_mod = {}
                        try:
                            lm_rows = cur.execute(
                                """
                                SELECT s.name AS SchemaName, t.name AS TableName, t.modify_date
                                FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id
                                """
                            ).fetchall()
                            for r in lm_rows:
                                last_mod[(r.SchemaName, r.TableName)] = str(r.modify_date)
                        except Exception:
                            last_mod = {}
                    from collections import defaultdict
                    by_table = defaultdict(list)
                    samples = {}
                    do_samples = ("samples" in scope)
                    for r in cols:
                        desc = xdesc.get((r.TABLE_SCHEMA, r.TABLE_NAME, r.COLUMN_NAME)) if xdesc else None
                        # annotate PK/FK in description for fallback
                        hints = []
                        if (r.TABLE_SCHEMA, r.TABLE_NAME) in pk and r.COLUMN_NAME in pk[(r.TABLE_SCHEMA, r.TABLE_NAME)]:
                            hints.append("PK")
                        if (r.TABLE_SCHEMA, r.TABLE_NAME, r.COLUMN_NAME) in fk:
                            rs, rt, rc = fk[(r.TABLE_SCHEMA, r.TABLE_NAME, r.COLUMN_NAME)]
                            hints.append(f"FK->{rs}.{rt}({rc})")
                        if r.COLUMN_NAME.lower().endswith("id"):
                            hints.append("hint:endswithId")
                        hint_str = (" | ".join(hints)) if hints else None
                        if do_samples and (not sel or (r.TABLE_SCHEMA.lower(), r.TABLE_NAME.lower()) in sel):
                            try:
                                with self.get_db_connection() as conn2:
                                    c2 = conn2.cursor()
                                    q = f"SELECT DISTINCT TOP (5) [{r.COLUMN_NAME}] FROM [{r.TABLE_SCHEMA}].[{r.TABLE_NAME}] WHERE [{r.COLUMN_NAME}] IS NOT NULL"
                                    vals = [str(v[0]) for v in c2.execute(q).fetchall()]
                                    if vals:
                                        samples[(r.TABLE_SCHEMA, r.TABLE_NAME, r.COLUMN_NAME)] = vals[:5]
                            except Exception:
                                pass
                        by_table[(r.TABLE_SCHEMA, r.TABLE_NAME)].append({
                            "OrdinalPos": int(r.ORDINAL_POSITION),
                            "ColumnName": r.COLUMN_NAME,
                            "DataType": r.DATA_TYPE,
                            "MaxLength": r.CHARACTER_MAXIMUM_LENGTH,
                            "IsNullable": 1 if r.IS_NULLABLE == 'YES' else 0,
                            "Description": (desc + (f" | {hint_str}" if hint_str else "")) if desc else hint_str
                        })
                    db_file = self._sqlite_path_from_env()
                    sconn = sqlite3.connect(db_file)
                    try:
                        self._fallback_sqlite_prepare(sconn)
                        up = 0
                        for t in tbls:
                            schema, name, ttype = t.TABLE_SCHEMA, t.TABLE_NAME, t.TABLE_TYPE
                            if sel and (schema.lower(), name.lower()) not in sel:
                                continue
                            tags = ["harvested"]
                            # optional row count
                            if "row_counts" in scope:
                                try:
                                    with self.get_db_connection() as conn2:
                                        c2 = conn2.cursor(); rc = c2.execute(f"SELECT COUNT(*) FROM [{schema}].[{name}]").fetchone()[0]
                                        tags.append(f"RowCount={int(rc)}")
                                except Exception:
                                    pass
                            # last modified
                            if last_mod.get((schema, name)):
                                tags.append(f"LastModified={last_mod[(schema, name)]}")
                            asset = {
                                "Kind": "Table" if ttype.upper().startswith("BASE") else "View",
                                "Source": source_name,
                                "SchemaName": schema,
                                "ObjectName": name,
                                "DisplayName": name,
                                "Sensitivity": "Internal",
                                "TagsJson": tags,
                            }
                            # enrich samples into column descriptions
                            cols_for_tbl = by_table.get((schema, name), [])
                            if do_samples:
                                for cd in cols_for_tbl:
                                    key = (schema, name, cd["ColumnName"])
                                    if key in samples:
                                        sv = ", ".join(samples[key])
                                        cd["Description"] = ((cd.get("Description") or "") + (" | " if cd.get("Description") else "") + f"samples: {sv}").strip()
                            asset_id = self._fallback_upsert_asset(sconn, asset)
                            self._fallback_upsert_columns(sconn, asset_id, cols_for_tbl)
                            up += 1
                    finally:
                        sconn.close()
                    return jsonify({
                        "status": "success",
                        "mode": "fallback_sqlite",
                        "assets_upserted": up,
                        "sqlite_path": db_file,
                    }), 200
                except Exception as e:
                    self.logger.error(f"[meta] harvest fallback failed: {e}", exc_info=True)
                    return jsonify({"status": "error", "message": str(e)}), 500

            count = 0
            try:
                with self.get_db_connection() as conn, self.MetaSession() as ms:
                    cur = conn.cursor()
                    # tables/views
                    tbls = cur.execute("""
                        SELECT t.TABLE_SCHEMA, t.TABLE_NAME, t.TABLE_TYPE
                        FROM INFORMATION_SCHEMA.TABLES t
                        ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME
                    """).fetchall()
                    # columns
                    cols = cur.execute("""
                        SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.ORDINAL_POSITION,
                               c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH, c.IS_NULLABLE
                        FROM INFORMATION_SCHEMA.COLUMNS c
                        ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
                    """).fetchall()
                    # extended properties (optional)
                    xdesc = {}
                    if "descriptions" in scope:
                        try:
                            xp = cur.execute("""
                                SELECT s.name AS SchemaName, t.name AS TableName, c.name AS ColumnName, ep.value AS Description
                                FROM sys.extended_properties ep
                                JOIN sys.tables t ON ep.major_id = t.object_id
                                JOIN sys.schemas s ON t.schema_id = s.schema_id
                                LEFT JOIN sys.columns c ON c.object_id = t.object_id AND ep.minor_id = c.column_id
                                WHERE ep.name = 'MS_Description';
                            """).fetchall()
                            for r in xp:
                                key = (r.SchemaName, r.TableName, r.ColumnName or "")
                                xdesc[key] = r.Description
                        except Exception:
                            xdesc = {}
                    # primary keys
                    pk = {}
                    try:
                        pk_rows = cur.execute("""
                            SELECT tc.TABLE_SCHEMA, tc.TABLE_NAME, kcu.COLUMN_NAME
                            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                            WHERE tc.CONSTRAINT_TYPE='PRIMARY KEY'
                        """).fetchall()
                        for r in pk_rows:
                            pk.setdefault((r.TABLE_SCHEMA, r.TABLE_NAME), set()).add(r.COLUMN_NAME)
                    except Exception:
                        pk = {}
                    # foreign keys
                    fk = {}
                    if "foreign_keys" in scope:
                        try:
                            fk_rows = cur.execute("""
                                SELECT sch1.name AS SchemaName, tab1.name AS TableName, col1.name AS ColumnName,
                                       sch2.name AS RefSchemaName, tab2.name AS RefTableName, col2.name AS RefColumnName
                                FROM sys.foreign_key_columns fkc
                                JOIN sys.tables tab1 ON tab1.object_id = fkc.parent_object_id
                                JOIN sys.schemas sch1 ON sch1.schema_id = tab1.schema_id
                                JOIN sys.columns col1 ON col1.column_id = fkc.parent_column_id AND col1.object_id = tab1.object_id
                                JOIN sys.tables tab2 ON tab2.object_id = fkc.referenced_object_id
                                JOIN sys.schemas sch2 ON sch2.schema_id = tab2.schema_id
                                JOIN sys.columns col2 ON col2.column_id = fkc.referenced_column_id AND col2.object_id = tab2.object_id
                            """).fetchall()
                            for r in fk_rows:
                                fk[(r.SchemaName, r.TableName, r.ColumnName)] = (r.RefSchemaName, r.RefTableName, r.RefColumnName)
                        except Exception:
                            fk = {}
                    # last modified per table
                    last_mod = {}
                    try:
                        lm_rows = cur.execute("""
                            SELECT s.name AS SchemaName, t.name AS TableName, t.modify_date
                            FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id
                        """).fetchall()
                        for r in lm_rows:
                            last_mod[(r.SchemaName, r.TableName)] = str(r.modify_date)
                    except Exception:
                        last_mod = {}

                    from collections import defaultdict
                    by_table = defaultdict(list)
                    samples = {}
                    do_samples = ("samples" in scope)
                    for r in cols:
                        by_table[(r.TABLE_SCHEMA, r.TABLE_NAME)].append({
                            "OrdinalPos": int(r.ORDINAL_POSITION),
                            "ColumnName": r.COLUMN_NAME,
                            "DataType": r.DATA_TYPE,
                            "MaxLength": r.CHARACTER_MAXIMUM_LENGTH,
                            "IsNullable": 1 if r.IS_NULLABLE == 'YES' else 0,
                            "Description": xdesc.get((r.TABLE_SCHEMA, r.TABLE_NAME, r.COLUMN_NAME))
                        })
                        if do_samples and (not sel or (r.TABLE_SCHEMA.lower(), r.TABLE_NAME.lower()) in sel):
                            try:
                                q = f"SELECT DISTINCT TOP (5) [{r.COLUMN_NAME}] FROM [{r.TABLE_SCHEMA}].[{r.TABLE_NAME}] WHERE [{r.COLUMN_NAME}] IS NOT NULL"
                                vals = [str(v[0]) for v in cur.execute(q).fetchall()]
                                if vals:
                                    samples[(r.TABLE_SCHEMA, r.TABLE_NAME, r.COLUMN_NAME)] = vals[:5]
                            except Exception:
                                pass

                    sel = self._selected_table_set()
                    for t in tbls:
                        schema, name, ttype = t.TABLE_SCHEMA, t.TABLE_NAME, t.TABLE_TYPE
                        if sel and (schema.lower(), name.lower()) not in sel:
                            continue
                        tags = ["harvested"]
                        if "row_counts" in scope:
                            try:
                                rc = cur.execute(f"SELECT COUNT(*) FROM [{schema}].[{name}]").fetchone()[0]
                                tags.append(f"RowCount={int(rc)}")
                            except Exception:
                                pass
                        if last_mod.get((schema, name)):
                            tags.append(f"LastModified={last_mod[(schema, name)]}")
                        asset = {
                            "Kind": "Table" if ttype.upper().startswith("BASE") else "View",
                            "Source": source_name,
                            "SchemaName": schema,
                            "ObjectName": name,
                            "DisplayName": name,
                            "Description": xdesc.get((schema, name, ""), None),
                            "OwnerEmail": None,
                            "Sensitivity": "Internal",
                            "TagsJson": tags,
                            "IsActive": True,
                        }
                        asset_id = self.upsert_asset(ms, asset)
                        # track for pruning inactive assets post upsert
                        try:
                            harvested_keys.add((schema, name))
                        except NameError:
                            harvested_keys = set(); harvested_keys.add((schema, name))
                        # enrich columns with PK/FK hints
                        cols_in_table = by_table.get((schema, name), [])
                        for cd in cols_in_table:
                            # Attach PK flag via Description hint; ColumnDef has IsKey as well, but upsert_columns signature accepts dict with keys matching model
                            if (schema, name) in pk and cd["ColumnName"] in pk[(schema, name)]:
                                cd.setdefault("IsKey", True)
                                desc = cd.get("Description") or ""
                                cd["Description"] = (desc + (" | " if desc else "") + "PK").strip()
                            if (schema, name, cd["ColumnName"]) in fk:
                                rs, rt, rc = fk[(schema, name, cd["ColumnName"])]
                                desc = cd.get("Description") or ""
                                cd["Description"] = (desc + (" | " if desc else "") + f"FK->{rs}.{rt}({rc})").strip()
                            if cd["ColumnName"].lower().endswith("id"):
                                desc = cd.get("Description") or ""
                                cd["Description"] = (desc + (" | " if desc else "") + "hint:endswithId").strip()
                            if do_samples:
                                key = (schema, name, cd["ColumnName"]) 
                                if key in samples:
                                    sv = ", ".join(samples[key])
                                    desc2 = cd.get("Description") or ""
                                    cd["Description"] = (desc2 + (" | " if desc2 else "") + f"samples: {sv}").strip()
                        self.upsert_columns(ms, asset_id, cols_in_table)
                        self.publish_event(ms, "schema.change", {"asset_id": asset_id}, {"AssetId": asset_id})
                        count += 1
                    # Prune assets for this source that were not seen in this harvest (multi-source friendly)
                    try:
                        if 'harvested_keys' in locals():
                            stale = (
                                ms.query(self.Asset)
                                .filter(self.Asset.Source == source_name, self.Asset.IsActive.is_(True))
                                .all()
                            )
                            for a in stale:
                                key = (a.SchemaName or '', a.ObjectName)
                                if key not in harvested_keys:
                                    a.IsActive = False
                        ms.commit()
                    except Exception:
                        ms.rollback(); ms.commit()
                    
                    ms.commit()
                return jsonify({"status": "success", "mode": "store_sqlalchemy", "assets_upserted": count}), 200
            except Exception as e:
                self.logger.error(f"[meta] harvest failed: {e}", exc_info=True)
                return jsonify({"status": "error", "message": str(e)}), 500

        @bp.route("/api/metadata/health", methods=["GET"])
        def metadata_health():
            # Report state and sqlite file path if applicable
            info = {
                "routes_loaded": bool(self._routes_loaded),
                "store_loaded": bool(self._store_loaded),
                "orch_loaded": bool(self._orch_loaded),
            }
            try:
                db_url = None
                if self._store_loaded:
                    try:
                        import metadata_store as ms
                        db_url = getattr(ms, "DB_URL", None)
                    except Exception:
                        pass
                if not db_url:
                    db_url = os.getenv("META_DB_URL", "sqlite:///./metadata.db")
                info["db_url"] = db_url
                if db_url.startswith("sqlite"):
                    path = db_url.split("sqlite:///")[-1]
                    info["sqlite_path"] = path
                    info["sqlite_exists"] = os.path.exists(path)
            except Exception:
                pass
            return jsonify(info), 200

        @bp.route("/api/metadata/assets_fallback", methods=["GET"])
        def assets_fallback():
            try:
                import sqlite3
                db_file = self._sqlite_path_from_env()
                conn = sqlite3.connect(db_file)
                try:
                    cur = conn.cursor()
                    rows = cur.execute(
                        "SELECT AssetId, Kind, Source, SchemaName, ObjectName, DisplayName, Sensitivity, UpdatedAt FROM mm_asset ORDER BY UpdatedAt DESC LIMIT 100"
                    ).fetchall()
                    results = [
                        {
                            "AssetId": r[0],
                            "Kind": r[1],
                            "Key": f"{r[2]}:{(r[3] + '.' if r[3] else '')}{r[4]}",
                            "DisplayName": r[5] or r[4],
                            "Sensitivity": r[6],
                            "UpdatedAt": r[7],
                        }
                        for r in rows
                    ]
                    return jsonify({"results": results}), 200
                finally:
                    conn.close()
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        # Register frontend-compatible fallback endpoints only if metadata_routes
        # failed to load. This prevents route duplication when the full store is available.
        if not self._routes_loaded:
            @bp.route("/api/metadata/assets", methods=["GET"])
            def assets_search_fallback():
                q = (request.args.get("q") or "").strip().lower()
                limit = int(request.args.get("limit") or 25)
                try:
                    import sqlite3
                    db_file = self._sqlite_path_from_env()
                    conn = sqlite3.connect(db_file)
                    try:
                        conn.row_factory = sqlite3.Row
                        cur = conn.cursor()
                        rows = cur.execute(
                            "SELECT AssetId, Kind, Source, SchemaName, ObjectName, DisplayName, Description, Sensitivity, UpdatedAt "
                            "FROM mm_asset ORDER BY UpdatedAt DESC LIMIT ?",
                            (limit,)
                        ).fetchall()
                        results = []
                        for r in rows:
                            text = " ".join(str(x or "") for x in (r["ObjectName"], r["DisplayName"], r["Description"], r["Source"]))
                            if q and q not in text.lower():
                                continue
                            results.append({
                                "AssetId": r["AssetId"],
                                "Kind": r["Kind"],
                                "Key": f"{r['Source']}:{(r['SchemaName'] + '.' if r['SchemaName'] else '')}{r['ObjectName']}",
                                "DisplayName": r["DisplayName"] or r["ObjectName"],
                                "Description": r["Description"],
                                "Sensitivity": r["Sensitivity"],
                                "UpdatedAt": r["UpdatedAt"],
                                "Tags": [],
                            })
                            if len(results) >= limit:
                                break
                        return jsonify({"results": results}), 200
                    finally:
                        conn.close()
                except Exception as e:
                    return jsonify({"error": str(e)}), 500

            @bp.route("/api/metadata/assets/<int:asset_id>", methods=["GET"])
            def asset_detail_fallback(asset_id: int):
                try:
                    import sqlite3
                    db_file = self._sqlite_path_from_env()
                    conn = sqlite3.connect(db_file)
                    try:
                        conn.row_factory = sqlite3.Row
                        cur = conn.cursor()
                        a = cur.execute(
                            "SELECT * FROM mm_asset WHERE AssetId=?", (asset_id,)
                        ).fetchone()
                        if not a:
                            return jsonify({"error": "Not found"}), 404
                        cols = cur.execute(
                            "SELECT ColumnName, OrdinalPos, DataType, MaxLength, IsNullable, Description, UpdatedAt "
                            "FROM mm_column WHERE AssetId=? ORDER BY OrdinalPos ASC",
                            (asset_id,)
                        ).fetchall()
                        data = {
                            "Asset": {
                                "AssetId": a["AssetId"],
                                "Kind": a["Kind"],
                                "Key": f"{a['Source']}:{(a['SchemaName'] + '.' if a['SchemaName'] else '')}{a['ObjectName']}",
                                "DisplayName": a["DisplayName"] or a["ObjectName"],
                                "Description": a["Description"],
                                "OwnerEmail": a["OwnerEmail"],
                                "Sensitivity": a["Sensitivity"],
                                "Version": a["Version"],
                                "UpdatedAt": a["UpdatedAt"],
                                "Tags": json.loads(a["TagsJson"]) if a["TagsJson"] else [],
                            },
                            "Columns": [
                                {
                                    "ColumnName": c["ColumnName"],
                                    "OrdinalPos": c["OrdinalPos"],
                                    "DataType": c["DataType"],
                                    "MaxLength": c["MaxLength"],
                                    "IsNullable": bool(c["IsNullable"]),
                                    "Description": c["Description"],
                                }
                                for c in cols
                            ],
                        }
                        return jsonify(data), 200
                    finally:
                        conn.close()
                except Exception as e:
                    return jsonify({"error": str(e)}), 500

        @bp.route("/api/metadata/bkg", methods=["GET"])
        def export_business_knowledge_graph():
            try:
                # Collect assets
                entities = []
                columns_by_entity = {}
                rels = []
                # Helper: prettify names
                def pretty(name: str) -> str:
                    try:
                        s = str(name or "").replace("_", " ").replace("-", " ")
                        # strip common prefixes
                        for pref in ("ECS ", "CT ", "MPV ", "Q "):
                            if s.upper().startswith(pref):
                                s = s[len(pref):]
                                break
                        return s.title()
                    except Exception:
                        return str(name or "")
                # Simple domain heuristics by table prefix
                def domain_for(schema: str, table: str) -> str:
                    t = (table or "").upper()
                    if t.startswith("ECS_"):
                        return "Claims"
                    if t.startswith("CT_"):
                        return "CoreTransactions"
                    if t.startswith("MPV_"):
                        return "Vendors"
                    if t.startswith("Q_"):
                        return "Quality"
                    return "General"

                if self._store_loaded and self.MetaSession:
                    with self.MetaSession() as s:
                        try:
                            all_rows = self.search_assets(s, q="", limit=10000) if callable(getattr(self, 'search_assets', None)) else []
                        except Exception:
                            all_rows = []
                        for a in all_rows:
                            key = a.get("Key") or ""
                            src = a.get("Key", "").split(":")[0] if a.get("Key") else None
                            schema_table = (key.split(":",1)[1] if ":" in key else "")
                            schema, table = (schema_table.split(".",1) + [None])[:2] if schema_table else (a.get("SchemaName"), a.get("ObjectName"))
                            ent = {
                                "id": int(a.get("AssetId")),
                                "key": key,
                                "source": src,
                                "schema": schema,
                                "table": table or a.get("DisplayName"),
                                "name": pretty(a.get("DisplayName") or a.get("ObjectName")),
                                "description": a.get("Description"),
                                "domain": domain_for(schema or "", (table or "")),
                                "tags": a.get("Tags") or []
                            }
                            entities.append(ent)
                            detail = self.get_asset_detail(s, int(a.get("AssetId"))) or {}
                            cols = []
                            for c in (detail.get("Columns") or []):
                                cols.append({
                                    "name": c.get("ColumnName"),
                                    "type": c.get("DataType"),
                                    "nullable": bool(c.get("IsNullable")),
                                    "is_key": bool(c.get("IsKey", False)),
                                    "description": c.get("Description")
                                })
                                # Parse FK hints
                                d = c.get("Description") or ""
                                m = re.search(r"FK->([\w]+)\.([\w]+)\(([\w]+)\)", d)
                                if m:
                                    rels.append({
                                        "from": {"entity": key, "column": c.get("ColumnName")},
                                        "to": {"entity": f"{src}:{m.group(1)}.{m.group(2)}", "column": m.group(3)},
                                        "type": "fk",
                                        "confidence": 1.0
                                    })
                            columns_by_entity[key] = cols
                else:
                    # Fallback sqlite
                    import sqlite3
                    db_file = self._sqlite_path_from_env()
                    conn = sqlite3.connect(db_file)
                    try:
                        conn.row_factory = sqlite3.Row
                        cur = conn.cursor()
                        rows = cur.execute("SELECT AssetId, Kind, Source, SchemaName, ObjectName, DisplayName, Description, Sensitivity, UpdatedAt, TagsJson FROM mm_asset").fetchall()
                        for a in rows:
                            key = f"{a['Source']}:{(a['SchemaName'] + '.' if a['SchemaName'] else '')}{a['ObjectName']}"
                            ent = {
                                "id": int(a["AssetId"]),
                                "key": key,
                                "source": a["Source"],
                                "schema": a["SchemaName"],
                                "table": a["ObjectName"],
                                "name": pretty(a["DisplayName"] or a["ObjectName"]),
                                "description": a["Description"],
                                "domain": domain_for(a["SchemaName"] or "", a["ObjectName"] or ""),
                                "tags": (json.loads(a["TagsJson"]) if a["TagsJson"] else [])
                            }
                            entities.append(ent)
                            cols = cur.execute("SELECT ColumnName, DataType, MaxLength, IsNullable, Description FROM mm_column WHERE AssetId=? ORDER BY OrdinalPos", (a["AssetId"],)).fetchall()
                            c_list = []
                            for c in cols:
                                c_list.append({
                                    "name": c["ColumnName"],
                                    "type": c["DataType"],
                                    "nullable": bool(c["IsNullable"]),
                                    "is_key": ("PK" in (c["Description"] or "")),
                                    "description": c["Description"],
                                })
                                d = c["Description"] or ""
                                m = re.search(r"FK->([\w]+)\.([\w]+)\(([\w]+)\)", d)
                                if m:
                                    rels.append({
                                        "from": {"entity": key, "column": c["ColumnName"]},
                                        "to": {"entity": f"{a['Source']}:{m.group(1)}.{m.group(2)}", "column": m.group(3)},
                                        "type": "fk",
                                        "confidence": 1.0
                                    })
                            columns_by_entity[key] = c_list
                    finally:
                        conn.close()

                # Synonym clusters (static + heuristic based on names)
                synonym_groups = [
                    {"terms": ["Store","Site","Outlet"]},
                    {"terms": ["Item","SKU","Article"]},
                    {"terms": ["Vendor","Supplier"]},
                ]

                # KPIs (simple examples based on known table names)
                kpis = []
                for e in entities:
                    t = (e.get("table") or "").upper()
                    if "CLAIM" in t:
                        kpis.append({
                            "id": f"kpi.claim_count.{e['table'].lower()}",
                            "name": "Claim Count",
                            "formula": f"COUNT(*) FROM [{e['schema']}].[{e['table']}]",
                            "grain": f"row:[{e['schema']}].[{e['table']}]",
                            "lineage": [{"entity": e["key"], "columns": ["*"]}],
                        })
                    if "SALES" in t:
                        kpis.append({
                            "id": f"kpi.sales_count.{e['table'].lower()}",
                            "name": "Sales Count",
                            "formula": f"COUNT(*) FROM [{e['schema']}].[{e['table']}]",
                            "grain": f"row:[{e['schema']}].[{e['table']}]",
                            "lineage": [{"entity": e["key"], "columns": ["*"]}],
                        })

                bkg = {
                    "version": 1,
                    "entities": entities,
                    "attributes": columns_by_entity,
                    "relationships": rels,
                    "synonyms": synonym_groups,
                    "kpis": kpis,
                }
                return jsonify(bkg), 200
            except Exception as e:
                self.logger.error(f"[meta] BKG export failed: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500

        self.app.register_blueprint(bp)
        self.logger.info("[meta] Registered /api/metadata/harvest")

    # ---------- Internal: FAISS + embeddings ----------
    def _init_meta_faiss(self):
        """Create the FAISS index for metadata paragraphs if available."""
        if faiss is None:
            self.logger.warning("[meta] FAISS not installed; metadata vectors disabled.")
            return
        self.meta_faiss_index = faiss.IndexIDMap2(faiss.IndexFlatL2(self.META_DIM))
        self.logger.info(f"[meta] Metadata FAISS index ready (dim={self.META_DIM}).")

    def _encode_texts(self, texts: T.List[str]):
        """Encode a list of strings with the provided embedder (float32)."""
        if self.embedder is None or np is None:
            return None
        try:
            out = self.embedder.encode(texts, batch_size=8)
            vecs = out["dense_vecs"] if isinstance(out, dict) and "dense_vecs" in out else out
            return np.asarray(vecs, dtype="float32")
        except Exception as e:
            self.logger.error(f"[meta] encode failed: {e}")
            return None

    def _build_metadata_paragraph(self, asset_id: int) -> str:
        """Construct a compact paragraph for a single asset.

        Intended to give the LLM a gist: name, description, sensitivity, tags
        and the first handful of columns (with types & optional descriptions).
        """
        try:
            detail = self.get_asset_detail(self.MetaSession(), asset_id) if callable(self.get_asset_detail) else {}
        except Exception:
            # fallback: open session manually (in case the above call signature differs)
            with self.MetaSession() as s:
                detail = self.get_asset_detail(s, asset_id)
        if not detail:
            return ""
        a = detail["Asset"]; cols = detail["Columns"][:20]
        """
        col_str = "; ".join(
            f"{c['ColumnName']} ({c['DataType']}{'' if c['MaxLength'] is None else f'({c['MaxLength']})'})"
            + (f' – {c.get('Description','')}' if c.get("Description") else "")
            for c in cols
        ) or "no columns found"
        """
        # Re-implemented column summary safely for Python 3.11
        def _fmt_col(c: dict) -> str:
            name = c.get('ColumnName')
            dtype = c.get('DataType')
            maxlen = c.get('MaxLength')
            desc = c.get('Description')
            size = '' if maxlen is None else f"({maxlen})"
            desc_part = f" – {desc}" if desc else ''
            return f"{name} ({dtype}{size}){desc_part}"

        col_str = "; ".join(_fmt_col(c) for c in cols) or "no columns found"
        parts = [
            f"Asset: {a['DisplayName']} ({a['Kind']})",
            f"Key: {a['Key']}",
            f"Sensitivity: {a['Sensitivity']}",
            f"Description: {a.get('Description') or 'n/a'}",
            f"Tags: {', '.join(a.get('Tags', [])) if a.get('Tags') else 'n/a'}",
            f"Columns: {col_str}"
        ]
        return "\n".join(parts)

    def _reembed_metadata_asset(self, asset_id: int):
        """Re-encode a single asset paragraph and push it into FAISS."""
        if faiss is None or self.meta_faiss_index is None:
            return
        text = self._build_metadata_paragraph(asset_id)
        if not text.strip():
            return
        vecs = self._encode_texts([text])
        if vecs is None:
            return
        ids = np.array([asset_id], dtype="int64")
        self.meta_faiss_index.add_with_ids(vecs.reshape(1, -1), ids)
        self.logger.info(f"[meta] Re-embedded AssetId={asset_id}")

    def _retrieve_metadata_context(self, question: str, k: int = 5) -> str:
        """Nearest neighbor lookup for metadata paragraphs given the question."""
        if faiss is None or self.meta_faiss_index is None:
            return ""
        vecs = self._encode_texts([question])
        if vecs is None:
            return ""
        D, I = self.meta_faiss_index.search(vecs.reshape(1, -1), k)
        ids = [int(i) for i in I[0] if i != -1]
        paras = []
        for asset_id in ids:
            paras.append(self._build_metadata_paragraph(asset_id))
        return "\n\n---\n\n".join([p for p in paras if p.strip()])

    # ---------- Internal: SQL table extractor ----------
    @staticmethod
    def _extract_tables_from_sql(sql: str):
        """Very small SQL FROM/JOIN parser used for lineage/telemetry."""
        patt = re.compile(r"(?:from|join)\s+(\[?\w+\]?\.\[?\w+\]?|\w+\.\w+|\[?\w+\]?)(?=\s|;|$)", re.IGNORECASE)
        raw = patt.findall(sql or "")
        cleaned = set()
        for t in raw:
            t = t.strip(" ;")
            if "." not in t:
                cleaned.add(f"dbo.{t.strip('[]')}")
            else:
                parts = [p.strip("[]") for p in t.split(".", 1)]
                cleaned.add(".".join(parts))
        return list(cleaned)

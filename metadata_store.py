"""metadata_store.py

Lightweight metadata registry using SQLAlchemy (SQLite by default).

What it stores:
- Assets (tables/views/files/models) with business metadata
- Columns for each asset
- Transformations and Lineage (optional, useful for provenance)
- Event log used by the background orchestrator

This module exposes a few helper functions for the rest of the app:
- init_db(): create tables and tune SQLite pragmas
- upsert_asset(), upsert_columns(): idempotent writes
- search_assets(), get_asset_detail(): read paths used by the UI and embedder
- publish_event(): append-only event signaling
"""
import os, json, hashlib
from datetime import datetime
from typing import List, Dict, Any

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, UniqueConstraint, BigInteger, DECIMAL, JSON, func
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# --- Config ---
DB_URL = os.getenv("META_DB_URL", "sqlite:///./metadata.db")  # change to postgres://... later

engine = create_engine(DB_URL, future=True, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

# --- Models ---
class Asset(Base):
    """A physical/logical data object (table, view, file, model)."""
    __tablename__ = "mm_asset"
    AssetId      = Column(Integer, primary_key=True)
    Kind         = Column(String(32),  nullable=False)                 # 'Table','View','Model','File'
    Source       = Column(String(128), nullable=False)                 # e.g. 'SqlServer:D365'
    SchemaName   = Column(String(128))
    ObjectName   = Column(String(256), nullable=False)
    DisplayName  = Column(String(256))
    Description  = Column(Text)
    OwnerEmail   = Column(String(256))
    Sensitivity  = Column(String(32), default="Internal", nullable=False)
    TagsJson     = Column(JSON)                                        # list[str]
    Version      = Column(Integer, default=1, nullable=False)
    IsActive     = Column(Boolean, default=True, nullable=False)
    CreatedAt    = Column(DateTime, default=datetime.utcnow, nullable=False)
    UpdatedAt    = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint('Source','SchemaName','ObjectName', name='u_asset_key'),)
    columns      = relationship("ColumnDef", back_populates="asset", cascade="all, delete-orphan")

class ColumnDef(Base):
    """Column-level details for each Asset.

    Includes profiling fields and flags (IsKey/IsPII) that can power governance
    and explanation features.
    """
    __tablename__ = "mm_column"
    ColumnId      = Column(Integer, primary_key=True)
    AssetId       = Column(Integer, ForeignKey("mm_asset.AssetId"), nullable=False)
    OrdinalPos    = Column(Integer, nullable=False)
    ColumnName    = Column(String(256), nullable=False)
    DataType      = Column(String(128), nullable=False)
    MaxLength     = Column(Integer)
    IsNullable    = Column(Boolean, nullable=False)
    Description   = Column(Text)
    IsKey         = Column(Boolean, default=False, nullable=False)
    IsPII         = Column(Boolean, default=False, nullable=False)
    ProfileRowCnt = Column(BigInteger)
    ProfileNullPct= Column(DECIMAL(5,2))
    ProfileMin    = Column(String(200))
    ProfileMax    = Column(String(200))
    UpdatedAt     = Column(DateTime, default=datetime.utcnow, nullable=False)
    asset         = relationship("Asset", back_populates="columns")

class Transformation(Base):
    """Optional metadata about data pipelines producing/consuming assets."""
    __tablename__ = "mm_transformation"
    TransformationId = Column(Integer, primary_key=True)
    Name         = Column(String(256), nullable=False)
    Tool         = Column(String(64),  nullable=False)      # 'SQL','Python','ADF','Agent'
    CodeRef      = Column(Text)
    OwnerEmail   = Column(String(256))
    ScheduleCron = Column(String(64))
    SLA_Minutes  = Column(Integer)
    CreatedAt    = Column(DateTime, default=datetime.utcnow, nullable=False)

class Lineage(Base):
    """Edges between Assets/Transformations to support provenance queries."""
    __tablename__ = "mm_lineage"
    LineageId    = Column(BigInteger, primary_key=True)
    FromType     = Column(String(16), nullable=False)       # 'Asset','Transformation'
    FromId       = Column(Integer, nullable=False)
    ToType       = Column(String(16), nullable=False)
    ToId         = Column(Integer, nullable=False)
    DetailJson   = Column(JSON)                             # optional column mapping
    CreatedAt    = Column(DateTime, default=datetime.utcnow, nullable=False)

class BusinessTerm(Base):
    __tablename__ = "mm_term"
    BusinessTermId = Column(Integer, primary_key=True)
    TermName     = Column(String(200), unique=True, nullable=False)
    Definition   = Column(Text, nullable=False)
    OwnerEmail   = Column(String(256))
    Status       = Column(String(32), default="Approved", nullable=False)  # 'Draft','Approved','Deprecated'
    CreatedAt    = Column(DateTime, default=datetime.utcnow, nullable=False)

class Event(Base):
    __tablename__ = "mm_event"
    # Use Integer autoincrement for SQLite compatibility
    EventId      = Column(Integer, primary_key=True, autoincrement=True)
    Topic        = Column(String(64), nullable=False)       # 'schema.change','profile.complete','lineage.upsert'
    KeyHash      = Column(String(40), nullable=False)       # sha1 idempotency key
    PayloadJson  = Column(JSON, nullable=False)
    CreatedAt    = Column(DateTime, default=datetime.utcnow, nullable=False)
    ProcessedAt  = Column(DateTime)
    Status       = Column(String(16), default="Pending", nullable=False)   # 'Pending','Done','Error'
    ErrorMessage = Column(Text)

# --- Init ---
def init_db():
    if DB_URL.startswith("sqlite"):
        with engine.connect() as con:
            con.exec_driver_sql("PRAGMA journal_mode=WAL;")
            con.exec_driver_sql("PRAGMA synchronous=NORMAL;")
            con.exec_driver_sql("PRAGMA temp_store=MEMORY;")
            con.exec_driver_sql("PRAGMA cache_size=-16000;")  # ~16MB
            # Lightweight migrations for evolving schema (SQLite only)
            try:
                cols = [r[1] for r in con.exec_driver_sql("PRAGMA table_info('mm_column')").fetchall()]
                if 'IsKey' not in cols:
                    con.exec_driver_sql("ALTER TABLE mm_column ADD COLUMN IsKey INTEGER NOT NULL DEFAULT 0")
                if 'IsPII' not in cols:
                    con.exec_driver_sql("ALTER TABLE mm_column ADD COLUMN IsPII INTEGER NOT NULL DEFAULT 0")
                if 'ProfileRowCnt' not in cols:
                    con.exec_driver_sql("ALTER TABLE mm_column ADD COLUMN ProfileRowCnt INTEGER")
                if 'ProfileNullPct' not in cols:
                    con.exec_driver_sql("ALTER TABLE mm_column ADD COLUMN ProfileNullPct REAL")
                if 'ProfileMin' not in cols:
                    con.exec_driver_sql("ALTER TABLE mm_column ADD COLUMN ProfileMin TEXT")
                if 'ProfileMax' not in cols:
                    con.exec_driver_sql("ALTER TABLE mm_column ADD COLUMN ProfileMax TEXT")
            except Exception:
                # Best-effort; ignore if table doesn't exist yet. create_all() covers fresh DBs.
                pass
    Base.metadata.create_all(bind=engine)

# --- Helpers ---
def sha1_key(obj: Dict[str, Any]) -> str:
    """Stable key hashing for event dedupe."""
    data = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(data).hexdigest()

def upsert_asset(session, asset: Dict[str, Any]) -> int:
    """Create or update an asset row and return its id.

    - Version is bumped when any field changes (simple optimistic versioning).
    """
    key = {"Source": asset["Source"], "SchemaName": asset.get("SchemaName"), "ObjectName": asset["ObjectName"]}
    row = session.query(Asset).filter_by(**key).one_or_none()
    now = datetime.utcnow()
    if row is None:
        row = Asset(**asset, Version=1, CreatedAt=now, UpdatedAt=now)
        session.add(row); session.flush()
        return row.AssetId
    changed = False
    for k, v in asset.items():
        if getattr(row, k) != v:
            setattr(row, k, v); changed = True
    if changed:
        row.Version = int(row.Version or 1) + 1
        row.UpdatedAt = now
    session.flush()
    return row.AssetId

def upsert_columns(session, asset_id: int, columns: List[Dict[str, Any]]):
    """Idempotent upsert for a batch of columns of a given asset."""
    existing = {c.ColumnName: c for c in session.query(ColumnDef).filter_by(AssetId=asset_id).all()}
    now = datetime.utcnow()
    for cd in columns:
        name = cd["ColumnName"]
        cur = existing.get(name)
        if cur is None:
            session.add(ColumnDef(AssetId=asset_id, UpdatedAt=now, **cd))
        else:
            touched = False
            for k, v in cd.items():
                if getattr(cur, k) != v:
                    setattr(cur, k, v); touched = True
            if touched: cur.UpdatedAt = now
    session.flush()

def publish_event(session, topic: str, key_obj: Dict[str, Any], payload: Dict[str, Any]) -> str:
    """Insert a unique event if not already present (by topic + key hash).

    Handles older SQLite schemas where the EventId column isn't autoincrement
    by computing the next id on the fly.
    """
    key = sha1_key(key_obj)
    exists = session.query(Event).filter_by(Topic=topic, KeyHash=key).one_or_none()
    if exists:
        return key
    ev = Event(Topic=topic, KeyHash=key, PayloadJson=payload, Status="Pending")
    try:
        session.add(ev)
        session.flush()
        return key
    except Exception as e:
        # Fallback for SQLite schemas missing INTEGER PRIMARY KEY AUTOINCREMENT
        if "mm_event.EventId" in str(e) or "EventId" in str(e):
            try:
                session.rollback()
            except Exception:
                pass
            try:
                next_id = (session.query(func.max(Event.EventId)).scalar() or 0) + 1
            except Exception:
                next_id = 1
            ev = Event(EventId=int(next_id), Topic=topic, KeyHash=key, PayloadJson=payload, Status="Pending")
            session.add(ev)
            session.flush()
            return key
        raise

def search_assets(session, q: str = "", limit: int = 25, source: str | None = None, active_only: bool = True):
    """Basic search used by UI. Returns a compact shape for cards/lists.

    - source: when provided, restrict to a single metadata source (e.g. 'SqlServer:MyDB')
    - active_only: filter to IsActive=True by default to hide deprecated rows
    """
    qry = session.query(Asset)
    if source:
        qry = qry.filter(Asset.Source == source)
    if active_only:
        qry = qry.filter(Asset.IsActive.is_(True))
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            (Asset.ObjectName.ilike(like)) |
            (Asset.DisplayName.ilike(like)) |
            (Asset.Description.ilike(like)) |
            (Asset.Source.ilike(like))
        )
    rows = qry.order_by(Asset.UpdatedAt.desc()).limit(limit).all()
    return [{
        "AssetId": a.AssetId,
        "Key": f"{a.Source}:{a.SchemaName}.{a.ObjectName}" if a.SchemaName else f"{a.Source}:{a.ObjectName}",
        "Kind": a.Kind,
        "DisplayName": a.DisplayName or a.ObjectName,
        "Description": a.Description,
        "OwnerEmail": a.OwnerEmail,
        "Sensitivity": a.Sensitivity,
        "Version": a.Version,
        "UpdatedAt": a.UpdatedAt.isoformat() if a.UpdatedAt else None,
        "Tags": a.TagsJson or []
    } for a in rows]

def list_sources(session) -> list[str]:
    """Return distinct metadata Sources present in the store, sorted by recent update."""
    # Prefer sources with most recent UpdatedAt
    from sqlalchemy import func as _func
    rows = (
        session.query(Asset.Source, _func.max(Asset.UpdatedAt))
        .group_by(Asset.Source)
        .order_by(_func.max(Asset.UpdatedAt).desc())
        .all()
    )
    return [r[0] for r in rows]

def get_asset_detail(session, asset_id: int):
    """Return a single asset with a tidy column list for detail panes."""
    a = session.query(Asset).filter_by(AssetId=asset_id).one_or_none()
    if not a: return {}
    cols = session.query(ColumnDef).filter_by(AssetId=asset_id).order_by(ColumnDef.OrdinalPos.asc()).all()
    return {
        "Asset": {
            "AssetId": a.AssetId,
            "Kind": a.Kind,
            "Key": f"{a.Source}:{a.SchemaName}.{a.ObjectName}" if a.SchemaName else f"{a.Source}:{a.ObjectName}",
            "DisplayName": a.DisplayName or a.ObjectName,
            "Description": a.Description,
            "OwnerEmail": a.OwnerEmail,
            "Sensitivity": a.Sensitivity,
            "Version": a.Version,
            "UpdatedAt": a.UpdatedAt.isoformat() if a.UpdatedAt else None,
            "Tags": a.TagsJson or []
        },
        "Columns": [{
            "ColumnName": c.ColumnName,
            "OrdinalPos": c.OrdinalPos,
            "DataType": c.DataType,
            "MaxLength": c.MaxLength,
            "IsNullable": bool(c.IsNullable),
            "Description": c.Description,
            "IsKey": bool(c.IsKey),
            "IsPII": bool(c.IsPII),
            "Profile": {
                "RowCount": int(c.ProfileRowCnt or 0) if c.ProfileRowCnt is not None else None,
                "NullPct": float(c.ProfileNullPct) if c.ProfileNullPct is not None else None,
                "Min": c.ProfileMin,
                "Max": c.ProfileMax
            }
        } for c in cols]
    }

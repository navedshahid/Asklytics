# catalog/refresh_catalog_tsql.py
import pyodbc, json, hashlib, time
from datetime import datetime
from collections import defaultdict
from pathlib import Path
import numpy as np

from retrieval.embed import embed_texts, save_faiss

def connect(dsn: str):
    return pyodbc.connect(dsn, timeout=5)

def fetchall(cursor, query, params=None):
    cursor.execute(query, params or [])
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]

def sha256_str(s: str) -> str:
    import hashlib as _h
    return "sha256:" + _h.sha256(s.encode("utf-8")).hexdigest()

def refresh_catalog(dsn: str, schemas: list[str] | None, out_dir: str, allowed_tables: set[str] | None = None):
    t0 = time.time()
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    cn = connect(dsn); cur = cn.cursor()

    schema_filter, params = "", []
    if schemas:
        schema_filter = "AND s.name IN ({})".format(",".join(["?"]*len(schemas)))
        params = schemas

    tables = fetchall(cur, f"""
        SELECT s.name AS schema_name, t.name AS table_name, t.object_id
        FROM sys.tables t
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        WHERE 1=1 {schema_filter}
        ORDER BY s.name, t.name
    """, params)

    # apply allowlist early
    if allowed_tables:
        tables = [t for t in tables if f"{t['schema_name']}.{t['table_name']}" in allowed_tables]

    rc = fetchall(cur, """
        SELECT p.object_id, SUM(p.row_count) AS row_count
        FROM sys.dm_db_partition_stats p
        JOIN sys.objects o ON o.object_id = p.object_id
        WHERE o.type = 'U'
        GROUP BY p.object_id
    """)
    rowcount_map = {r['object_id']: int(r['row_count']) for r in rc}

    table_list = []
    for t in tables:
        fq = f"{t['schema_name']}.{t['table_name']}"
        table_list.append({
            "name": fq, "schema": t['schema_name'],
            "row_count": rowcount_map.get(t['object_id'], 0),
            "description": "", "primary_key": [], "foreign_keys": [], "indexes": []
        })

    # columns, keys, fks, indexes (all filtered by allowed tables if provided)
    cols = fetchall(cur, f"""
        SELECT s.name AS schema_name, t.name AS table_name, c.name AS column_name,
               ty.name AS type_name, c.is_nullable, c.column_id, t.object_id
        FROM sys.columns c
        JOIN sys.tables t ON t.object_id = c.object_id
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        JOIN sys.types ty ON ty.user_type_id = c.user_type_id
        WHERE 1=1 {schema_filter}
        ORDER BY s.name, t.name, c.column_id
    """, params)
    if allowed_tables:
        cols = [c for c in cols if f"{c['schema_name']}.{c['table_name']}" in allowed_tables]

    pks = fetchall(cur, """
        SELECT s.name AS schema_name, t.name AS table_name, c.name AS column_name
        FROM sys.key_constraints k
        JOIN sys.tables t ON t.object_id = k.parent_object_id
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        JOIN sys.index_columns ic ON ic.object_id = t.object_id AND ic.index_id = k.unique_index_id
        JOIN sys.columns c ON c.object_id = t.object_id AND c.column_id = ic.column_id
        WHERE k.type = 'PK'
    """)
    if allowed_tables:
        pks = [pk for pk in pks if f"{pk['schema_name']}.{pk['table_name']}" in allowed_tables]

    fks = fetchall(cur, """
        SELECT s1.name AS schema_from, t1.name AS table_from, c1.name AS col_from,
               s2.name AS schema_to,   t2.name AS table_to,   c2.name AS col_to
        FROM sys.foreign_keys fk
        JOIN sys.tables t1 ON t1.object_id = fk.parent_object_id
        JOIN sys.schemas s1 ON s1.schema_id = t1.schema_id
        JOIN sys.tables t2 ON t2.object_id = fk.referenced_object_id
        JOIN sys.schemas s2 ON s2.schema_id = t2.schema_id
        JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
        JOIN sys.columns c1 ON c1.object_id = fkc.parent_object_id AND c1.column_id = fkc.parent_column_id
        JOIN sys.columns c2 ON c2.object_id = fkc.referenced_object_id AND c2.column_id = fkc.referenced_column_id
    """)
    if allowed_tables:
        fks = [fk for fk in fks
               if f"{fk['schema_from']}.{fk['table_from']}" in allowed_tables
               and f"{fk['schema_to']}.{fk['table_to']}" in allowed_tables]

    idx = fetchall(cur, """
        SELECT s.name AS schema_name, t.name AS table_name, i.name AS index_name, i.type_desc, ic.index_column_id, c.name AS col_name
        FROM sys.indexes i
        JOIN sys.tables t ON t.object_id = i.object_id
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        JOIN sys.index_columns ic ON ic.object_id = t.object_id AND ic.index_id = i.index_id
        JOIN sys.columns c ON c.object_id = t.object_id AND c.column_id = ic.column_id
        WHERE i.is_hypothetical = 0 AND i.is_disabled = 0
        ORDER BY s.name, t.name, i.name, ic.index_column_id
    """)
    if allowed_tables:
        idx = [r for r in idx if f"{r['schema_name']}.{r['table_name']}" in allowed_tables]

    # maps
    table_map = {t["name"]: t for t in table_list}
    for pk in pks:
        table_map[f"{pk['schema_name']}.{pk['table_name']}"]["primary_key"].append(pk["column_name"])
    relationships = defaultdict(lambda: {"from":"", "to":"", "via":[]})
    for fk in fks:
        f_from = f"{fk['schema_from']}.{fk['table_from']}"
        f_to   = f"{fk['schema_to']}.{fk['table_to']}"
        key = f"{f_from}->{f_to}"
        relationships[key]["from"]=f_from
        relationships[key]["to"]=f_to
        relationships[key]["via"].append({"from": fk["col_from"], "to": fk["col_to"]})
    index_map = defaultdict(list)
    for r in idx:
        index_map[f"{r['schema_name']}.{r['table_name']}"].append(
            {"name": r["index_name"], "type": r["type_desc"], "column": r["col_name"]}
        )
    for name, arr in index_map.items():
        if name in table_map:
            table_map[name]["indexes"] = arr

    # stats (JSON-safe)
    def _safe_num(v):
        try:
            if hasattr(v, "timestamp"): return float(v.timestamp())
            return float(v)
        except Exception: raise
    def _safe_str(v):
        try:
            if hasattr(v, "isoformat"): return v.isoformat()
            return str(v)
        except Exception:
            return repr(v)

    stats = {}
    for fq, t in table_map.items():
        schema, table = fq.split(".", 1)
        try:
            sample = fetchall(cur, f"SELECT TOP 10000 * FROM {schema}.{table} WITH (NOLOCK)")
        except Exception:
            sample = []
        if not sample: continue
        col_names = sample[0].keys()
        for c in col_names:
            vals = [row[c] for row in sample if row[c] is not None]
            if not vals:
                stats[(fq, c)] = {"null_ratio": 1.0}; continue
            null_ratio = 1 - (len(vals) / max(1, len(sample)))
            try:
                nums = [_safe_num(v) for v in vals]
                p50 = float(np.percentile(nums, 50))
                p95 = float(np.percentile(nums, 95))
                stats[(fq, c)] = {"null_ratio": float(null_ratio), "p50": p50, "p95": p95}
            except Exception:
                uniq = list(dict.fromkeys(vals))[:10]
                stats[(fq, c)] = {"null_ratio": float(null_ratio), "samples": [_safe_str(v) for v in uniq]}

    # outputs
    tables_out, columns_out = [], []
    for fq, t in table_map.items():
        table_cols = [c for c in cols if f"{c['schema_name']}.{c['table_name']}" == fq]
        for c in table_cols:
            key = (fq, c["column_name"])
            columns_out.append({
                "table": fq, "name": c["column_name"], "dtype": c["type_name"],
                "is_nullable": bool(c["is_nullable"]),
                "stats": stats.get(key, {"null_ratio": None}),
                "description": ""
            })
        tables_out.append(t)
    relationships_out = list(relationships.values())

    # embeddings
    col_texts = [
        f"{c['table']}.{c['name']} {c['dtype']} "
        f"{c.get('description','')} {json.dumps(c.get('stats', {}), ensure_ascii=False)}"
        for c in columns_out
    ]
    vecs = embed_texts(col_texts)
    save_faiss(Path(out_dir) / "columns.faiss", vecs)
    for i, c in enumerate(columns_out):
        c["embedding_hint"] = "faiss:index:" + str(i)

    # dictionary + version
    dictionary_out = {"terms": []}
    sig = sha256_str(json.dumps({"tables":tables_out,"columns":columns_out,"relationships":relationships_out}, ensure_ascii=False)[:100000])
    version = {"version": datetime.utcnow().isoformat()+"Z", "checksum": sig, "table_count": len(tables_out)}

    # write
    Path(out_dir, "tables.json").write_text(json.dumps({"tables": tables_out}, indent=2), encoding="utf-8")
    Path(out_dir, "columns.json").write_text(json.dumps({"columns": columns_out}, indent=2), encoding="utf-8")
    Path(out_dir, "relationships.json").write_text(json.dumps({"relationships": relationships_out}, indent=2), encoding="utf-8")
    Path(out_dir, "dictionary.json").write_text(json.dumps(dictionary_out, indent=2), encoding="utf-8")
    Path(out_dir, "version.json").write_text(json.dumps(version, indent=2), encoding="utf-8")

    return {"elapsed_sec": round(time.time()-t0, 2), **version}
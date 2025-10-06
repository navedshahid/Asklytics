# catalog/refresh_catalog_pg.py
import psycopg2, json, time
from pathlib import Path
from collections import defaultdict
import numpy as np
from retrieval.embed import embed_texts, save_faiss

def _fetchall(cur, q, args=None):
    cur.execute(q, args or [])
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def refresh_catalog(dsn: str, schemas: list[str] | None, out_dir: str):
    t0 = time.time()
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    cn = psycopg2.connect(dsn)
    cur = cn.cursor()

    schema_filter = " AND table_schema = ANY(%s) " if schemas else ""
    args = [schemas] if schemas else []

    tables = _fetchall(cur, f"""
      SELECT table_schema, table_name
      FROM information_schema.tables
      WHERE table_type='BASE TABLE' {schema_filter}
      ORDER BY 1,2
    """, args)

    # Rowcounts (approx) via reltuples
    stats = _fetchall(cur, """
      SELECT n.nspname AS schema, c.relname AS table, c.reltuples::bigint AS row_estimate
      FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE c.relkind='r'
    """)

    rowmap = {f"{s['schema']}.{s['table']}": int(s["row_estimate"]) for s in stats}
    tables_out = []
    for t in tables:
        fq = f"{t['table_schema']}.{t['table_name']}"
        tables_out.append({
            "name": fq, "schema": t["table_schema"],
            "row_count": rowmap.get(fq, 0),
            "description": "", "primary_key": [], "foreign_keys": [], "indexes": []
        })

    cols = _fetchall(cur, f"""
      SELECT table_schema, table_name, column_name, data_type, is_nullable
      FROM information_schema.columns
      WHERE 1=1 {schema_filter}
      ORDER BY table_schema, table_name, ordinal_position
    """, args)

    pks = _fetchall(cur, """
      SELECT n.nspname AS schema_name, t.relname AS table_name, a.attname AS column_name
      FROM pg_index i
      JOIN pg_class t ON t.oid = i.indrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
      JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey)
      WHERE i.indisprimary
    """)
    fks = _fetchall(cur, """
      SELECT
        n1.nspname AS schema_from, c1.relname AS table_from, a1.attname AS col_from,
        n2.nspname AS schema_to,   c2.relname AS table_to,   a2.attname AS col_to
      FROM pg_constraint con
      JOIN pg_class c1 ON c1.oid = con.conrelid
      JOIN pg_namespace n1 ON n1.oid = c1.relnamespace
      JOIN pg_class c2 ON c2.oid = con.confrelid
      JOIN pg_namespace n2 ON n2.oid = c2.relnamespace
      JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
      JOIN unnest(con.confkey) WITH ORDINALITY AS fk(attnum, ord) ON fk.ord = k.ord
      JOIN pg_attribute a1 ON a1.attrelid = c1.oid AND a1.attnum = k.attnum
      JOIN pg_attribute a2 ON a2.attrelid = c2.oid AND a2.attnum = fk.attnum
      WHERE con.contype='f'
    """)

    # Map + relationships
    table_map = {t["name"]: t for t in tables_out}
    for pk in pks:
        table_map[f"{pk['schema_name']}.{pk['table_name']}"]["primary_key"].append(pk["column_name"])
    from collections import defaultdict
    rels = defaultdict(lambda: {"from":"","to":"","via":[]})
    for fk in fks:
        f_from = f"{fk['schema_from']}.{fk['table_from']}"
        f_to   = f"{fk['schema_to']}.{fk['table_to']}"
        key = f"{f_from}->{f_to}"
        rels[key]["from"]=f_from; rels[key]["to"]=f_to
        rels[key]["via"].append({"from":fk["col_from"], "to":fk["col_to"]})

    # Column list + light samples (skip heavy sampling for MVP)
    columns_out=[]
    for c in cols:
        fq = f"{c['table_schema']}.{c['table_name']}"
        columns_out.append({
            "table": fq, "name": c["column_name"],
            "dtype": c["data_type"], "is_nullable": c["is_nullable"]=="YES",
            "stats": {}
        })

    # Embeddings
    import json as _j
    texts = [f"{c['table']}.{c['name']} {c['dtype']} {_j.dumps(c.get('stats',{}))}" for c in columns_out]
    vecs = embed_texts(texts)
    save_faiss(Path(out_dir)/"columns.faiss", vecs)

    Path(out_dir,"tables.json").write_text(json.dumps({"tables":tables_out}, indent=2))
    Path(out_dir,"columns.json").write_text(json.dumps({"columns":columns_out}, indent=2))
    Path(out_dir,"relationships.json").write_text(json.dumps({"relationships":list(rels.values())}, indent=2))
    Path(out_dir,"dictionary.json").write_text(json.dumps({"terms":[]}, indent=2))
    Path(out_dir,"version.json").write_text(json.dumps({"version":time.time()}, indent=2))
    return {"elapsed_sec": round(time.time()-t0,2)}

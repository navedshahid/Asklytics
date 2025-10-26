# table_profiles.py
from __future__ import annotations
import re
from typing import List, Tuple, Dict

def _name_tags(table_name: str) -> list[str]:
    n = table_name.lower()
    tags = []
    if any(k in n for k in ["init", "initiate", "staging", "tmp", "work"]):
        tags.append("init_like")
    if any(k in n for k in ["fact", "txn", "trans", "detail", "table"]):
        tags.append("fact_like_name")
    if any(k in n for k in ["dim", "ref", "lookup", "master"]):
        tags.append("dimension_like_name")
    return tags

def _column_tags(columns: List[Tuple[str, str]]) -> list[str]:
    tags = []
    colnames = [c[0].lower() for c in columns]
    dtypes = [c[1].lower() for c in columns]
    if any(c in colnames for c in ["transdate", "claimdate", "createdon", "createddate", "postingdate"]):
        tags.append("has_date")
    if sum(dt.startswith(("int","bigint","numeric","decimal","float","money")) for dt in dtypes) > max(1, len(dtypes)//2):
        tags.append("numeric_heavy")
    if any(c in colnames for c in ["status","isfinal","is_draft","draft"]):
        tags.append("has_status")
    return tags

def build_table_profiles_sqlserver(conn) -> list[dict]:
    """
    Returns list of profiles:
    [{ 'table': 'schema.table', 'row_count': int, 'tags': [...], 'text': 'profile text for embedding' }, ...]
    """
    cur = conn.cursor()

    col_rows = cur.execute("""
        SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.COLUMNS c
        ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
    """).fetchall()

    # MS_Description if present
    try:
        desc_rows = cur.execute("""
            SELECT
              s.name AS schema_name,
              t.name AS table_name,
              CAST(p.value AS NVARCHAR(MAX)) AS description
            FROM sys.tables t
            JOIN sys.schemas s ON s.schema_id = t.schema_id
            LEFT JOIN sys.extended_properties p
              ON p.major_id = t.object_id
             AND p.minor_id = 0
             AND p.name = 'MS_Description'
        """).fetchall()
        desc_map = {(r.schema_name, r.table_name): (r.description or "") for r in desc_rows}
    except Exception:
        desc_map = {}

    rowcount_rows = cur.execute("""
        SELECT s.name AS schema_name, t.name AS table_name, SUM(p.rows) AS row_count
        FROM sys.tables t
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1)
        GROUP BY s.name, t.name
    """).fetchall()
    rowcount_map = {(r.schema_name, r.table_name): int(r.row_count or 0) for r in rowcount_rows}

    # collect columns per table
    tables: Dict[tuple, list[tuple[str,str]]] = {}
    for r in col_rows:
        key = (r.TABLE_SCHEMA, r.TABLE_NAME)
        tables.setdefault(key, []).append((r.COLUMN_NAME, r.DATA_TYPE))

    profiles = []
    for (sch, tbl), cols in tables.items():
        fq = f"{sch}.{tbl}"
        name_tags = _name_tags(fq)
        col_tags = _column_tags(cols)
        rc = rowcount_map.get((sch, tbl), 0)
        desc = desc_map.get((sch, tbl), "")
        tags = set(name_tags + col_tags)
        if rc > 100_000:
            tags.add("large_table")
            tags.add("fact_like_stats")

        col_str = ", ".join([f"{c} {t}" for c, t in cols])
        tag_str = ", ".join(sorted(tags))
        profile_text = (
            f"Table {fq}. RowCount ~ {rc}. Tags: {tag_str}. "
            f"Description: {desc}. Columns: {col_str}."
        )
        profiles.append({
            "table": fq,
            "row_count": rc,
            "tags": sorted(tags),
            "text": profile_text
        })
    return profiles

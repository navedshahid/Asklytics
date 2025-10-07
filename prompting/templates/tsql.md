## Allowed Columns (strict)
{%- for t in retrieval.tables -%}
- {{ t }}:
  {%- for c in retrieval.columns if c.table == t -%}
  {{ " " ~ c.name }}{{ "," if not loop.last }}
  {%- endfor -%}
{%- endfor %}

## Rules (STRICT)
- Use only the tables/columns listed above.
- Schema-qualify tables (schema.table).
- One SELECT statement. No DDL/DML/EXEC/temp tables.
- Prefer TOP 50 for previews.

## Rules (STRICT)
- Return ONE T-SQL SELECT statement only.
- Do NOT wrap the SQL in quotes or code fences.
- Use only the allowed tables/columns listed above.
- Schema-qualify tables (schema.table).

## Output
Return only the SQL text.



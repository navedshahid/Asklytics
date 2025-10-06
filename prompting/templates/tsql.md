## Allowed Columns (strict)
{%- for t in retrieval.tables -%}
- {{ t }}:
  {%- for c in retrieval.columns if c.table == t -%}
  {{ " " ~ c.name }}{{ "," if not loop.last }}
  {%- endfor -%}
{%- endfor %}

## Rules (STRICT)
- You MUST use only the tables and columns listed above.
- If the question needs a column that is not listed, reply with: `CANNOT_ANSWER_MISSING_COLUMN`.
- Use schema-qualified names (schema.table).
- One SELECT statement only. No DDL, DML, EXEC, or temp tables.
- Prefer TOP 50 unless the user requests aggregates only.

## Output
Return only the SQL text.
You are generating **PostgreSQL SQL** (ANSI + PG functions).
Use ONLY the tables/columns listed.

## Question
{{ question }}

## Tables
{% for t in retrieval.tables %}- {{ t }}{% endfor %}

## Columns
{% for c in retrieval.columns %}- {{ c.table }}.{{ c.name }} ({{ c.dtype }}){% endfor %}

## Relationships
{% for r in retrieval.relationships %}- {{ r.from }} ⇄ {{ r.to }} via {{ ", ".join([v.from + "=" + v.to for v in r.via]) }}{% endfor %}

## Rules
{{ policies }}

## Output
- One SELECT query.
- Add `LIMIT 500` unless user specifies otherwise.
- Prefer `date_trunc('month', ts)` for monthly grouping.

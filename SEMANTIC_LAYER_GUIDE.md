# AskLytics Semantic Layer & Business Knowledge Graph

## Overview

The **Semantic Layer** is a business knowledge graph (BKG) that maps business terms—entities, metrics, relationships, and policies—to any physical schema. It enables:

- **Business-friendly queries**: Ask "What was our revenue last month?" → System uses pre-defined metric
- **Consistent metrics**: Finance and ops see the same "revenue" calculation
- **Governance**: PII masking and row filtering applied automatically during compilation
- **DB-agnostic**: Works with SQLite, DuckDB, PostgreSQL, MySQL, SQL Server

---

## Architecture

```
[User Question] 
    ↓
[Semantic Search] → Find matching metric/entity (FAISS + keyword)
    ↓
[Compile Metric] → Render SQL with joins, filters, time ranges, policies
    ↓
[Execute + Mask] → Apply PII masking, return results with provenance
```

### Components

| Component | Purpose |
|-----------|---------|
| **MDL (Model Definition Language)** | YAML files defining entities, metrics, relations, policies |
| **Semantic Engine** (`semantic/engine.py`) | Load MDL, build graph, compile metrics, vector search |
| **REST APIs** (`semantic_routes.py`) | `/semantic/health`, `/catalog`, `/search`, `/compile`, `/reindex` |
| **Modeling UI** (`/modeling`) | Visual ERD + relationship CRUD |
| **Planner Integration** | `/api/ask/stream` searches semantic layer before FAISS retrieval |

---

## Quick Start

### 1. Seed Sample Data (Retail Schema)

```bash
# SQLite
python scripts/seed_sqlite_retail.py

# DuckDB
python scripts/seed_duckdb_retail.py
```

This creates tables: `customers`, `orders`, `order_items`, `products`, `stores` with sample data.

### 2. Start AskLytics

```bash
python app.py
```

The semantic layer initializes automatically on startup.

### 3. Test Semantic Queries

Navigate to `http://localhost:5000` and ask:

- ✅ **"What was our gross revenue last month?"** → Uses `gross_revenue` metric
- ✅ **"Show me top 10 selling products"** → Uses `top_sellers` metric
- ✅ **"Count of orders by store"** → Uses `order_count` metric

When the system finds a semantic match (score > 0.7), you'll see:
> ✨ Using pre-compiled metric: gross_revenue

---

## MDL (Model Definition Language)

MDL files live in `/semantic/mdl/` with 4 subdirectories:

### Entities (`entities/*.yaml`)

Define business objects (tables).

**Example: `entities/orders.yaml`**

```yaml
name: orders
grain: order_id
description: Customer orders header table
reference:
  table: orders
columns:
  - { name: order_id, dtype: integer, primary: true, description: "Order primary key" }
  - { name: customer_id, dtype: integer, description: "Foreign key to customers" }
  - { name: store_id, dtype: integer, description: "Foreign key to stores" }
  - { name: order_date, dtype: timestamp, description: "Order creation timestamp" }
  - { name: status, dtype: string, description: "Order status (pending, completed, cancelled)" }
  - { name: total_amount, dtype: decimal, description: "Total order value" }
  - { name: shipping_address, dtype: string, pii: true, description: "Shipping address" }
properties:
  default_time_col: order_date
  default_filters:
    - "status != 'cancelled'"
tags:
  - transactional
  - order
```

### Metrics (`metrics/*.yaml`)

Define KPIs with templated SQL.

**Example: `metrics/gross_revenue.yaml`**

```yaml
name: gross_revenue
entity: order_items
grain: [day, store]
description: Sum of extended price before returns and discounts
sql: |
  SELECT
    DATE(o.order_date) AS day,
    o.store_id,
    SUM(oi.quantity * oi.unit_price) AS gross_revenue
  FROM orders o
  JOIN order_items oi ON oi.order_id = o.order_id
  WHERE o.order_date BETWEEN :start_date AND :end_date
    AND o.status != 'cancelled'
    {{AND_FILTERS}}
  GROUP BY DATE(o.order_date), o.store_id
filters:
  store: "o.store_id = :store"
  product: "oi.product_id = :product"
  category: "oi.product_id IN (SELECT product_id FROM products WHERE category = :category)"
lineage:
  - { table: "orders", column: "order_date" }
  - { table: "orders", column: "store_id" }
  - { table: "order_items", column: "quantity" }
  - { table: "order_items", column: "unit_price" }
examples:
  - "What was our gross revenue last month?"
  - "Show me daily revenue by store"
  - "Total sales for electronics category"
tags:
  - revenue
  - financial
```

**Placeholders:**

- `:start_date`, `:end_date` → Injected by compiler
- `{{AND_FILTERS}}` → Replaced with optional filter clauses
- `:store`, `:product` → User-provided filter values

### Relations (`relations/*.yaml`)

Define FK relationships.

**Example: `relations/orders_to_customers.yaml`**

```yaml
name: orders_customers
from:
  model: orders
  column: customer_id
to:
  model: customers
  column: customer_id
type: MANY_TO_ONE
condition: "orders.customer_id = customers.customer_id"
description: "Each order belongs to one customer; customers can have many orders"
tags:
  - transactional
```

### Policies (`policies/*.yaml`)

Define PII masking and row filters.

**Example: `policies/pii_masking.yaml`**

```yaml
name: mask_customer_pii
type: mask_column
description: Mask customer PII fields (email, phone, address) for non-pii_viewer roles
targets:
  - entity: customers
    column: email
    rule: "CASE WHEN 1=1 THEN SUBSTR(email, 1, 3) || '***@***' END"
  - entity: customers
    column: phone
    rule: "CASE WHEN 1=1 THEN '***-***-' || SUBSTR(phone, -4) END"
  - entity: customers
    column: first_name
    rule: "CASE WHEN 1=1 THEN SUBSTR(first_name, 1, 1) || '***' END"
  - entity: customers
    column: last_name
    rule: "CASE WHEN 1=1 THEN SUBSTR(last_name, 1, 1) || '***' END"
  - entity: orders
    column: shipping_address
    rule: "CASE WHEN 1=1 THEN '[REDACTED]' END"
roles_exempt:
  - pii_viewer
  - admin
tags:
  - pii
  - gdpr
  - compliance
```

---

## REST API Reference

### Health Check

```bash
GET /semantic/health
```

**Response:**

```json
{
  "status": "healthy",
  "last_loaded": "2024-10-30T08:19:00Z",
  "entities": 5,
  "metrics": 4,
  "relations": 4,
  "policies": 2,
  "semantic_index": "available",
  "errors": []
}
```

### Catalog

```bash
GET /semantic/catalog?type=metric&page=1&per_page=50
```

**Response:**

```json
{
  "metrics": [
    {
      "name": "gross_revenue",
      "description": "Sum of extended price before returns and discounts",
      "entity": "order_items",
      "grain": ["day", "store"],
      "examples": ["What was our gross revenue last month?"],
      "tags": ["revenue", "financial"]
    }
  ],
  "metrics_total": 4
}
```

### Search

```bash
POST /semantic/search
Content-Type: application/json

{
  "q": "revenue by store",
  "k": 5
}
```

**Response:**

```json
{
  "results": [
    {
      "type": "metric",
      "name": "gross_revenue",
      "description": "Sum of extended price before returns and discounts",
      "score": 0.92,
      "path": "metrics/gross_revenue",
      "metadata": { /* full metric definition */ }
    }
  ],
  "query": "revenue by store",
  "k": 5
}
```

### Compile Metric

```bash
POST /semantic/compile
Content-Type: application/json
X-Role: analyst

{
  "target": "gross_revenue",
  "filters": { "store": 1, "product": 42 },
  "time_range": { "start_date": "2024-01-01", "end_date": "2024-12-31" },
  "limit": 1000
}
```

**Response:**

```json
{
  "status": "success",
  "sql": "SELECT DATE(o.order_date) AS day, ...",
  "lineage": [
    { "table": "orders", "column": "order_date" },
    { "table": "order_items", "column": "quantity" }
  ],
  "grain": ["day", "store"],
  "warnings": [],
  "policies_applied": [
    { "policy": "mask_customer_pii", "type": "mask_column", "description": "..." }
  ],
  "metric": "gross_revenue",
  "entity": "order_items"
}
```

### Reindex

```bash
POST /semantic/reindex
X-Role: admin
```

Reloads MDL files and rebuilds semantic index. Call after adding/editing relations in the Modeling UI.

---

## Modeling UI

Navigate to `http://localhost:5000/modeling` to:

### View ERD

- See all entities (tables) as cards
- Shows columns, data types, tags
- Color-coded (blue for entities, green for metrics)

### Manage Relationships

**Create Relationship:**

1. Click **"+ Relationship"** button
2. Fill form:
   - **Name**: `orders_stores`
   - **From**: `orders.store_id`
   - **To**: `stores.store_id`
   - **Type**: `MANY_TO_ONE`
   - **Description**: (optional)
3. Click **"Save Relationship"**

The relationship is persisted to `/semantic/mdl/relations/orders_stores.yaml` and the engine hot-reloads.

**Edit/Delete:**

- Click **"⋮"** menu on any relationship card
- Confirm "OK" to edit, "Cancel" to delete

---

## Integration with NL→SQL Pipeline

When you ask a question via `/api/ask/stream`:

1. **Semantic Search** runs first:
   - Embedding-based search over entities/metrics/examples
   - If top hit is a **metric** with score > 0.7 → compile it
2. **Fallback to FAISS**: If no semantic match, use standard schema retrieval + LLM
3. **Governance**: Policies (PII masking, row filters) are always applied

**UI Notification:**

When a semantic match is found, you'll see in the chat:

> ✨ Using pre-compiled metric: gross_revenue

This ensures:
- **Consistent** metric definitions across users
- **Faster** queries (no LLM guessing)
- **Governed** results (policies pre-applied)

---

## Example Workflow

### Scenario: Define "Monthly Active Users" Metric

**1. Create Metric File** (`semantic/mdl/metrics/monthly_active_users.yaml`)

```yaml
name: monthly_active_users
entity: customers
grain: [month]
description: Count of distinct customers who placed at least one order in the month
sql: |
  SELECT
    DATE_TRUNC('month', o.order_date) AS month,
    COUNT(DISTINCT o.customer_id) AS monthly_active_users
  FROM orders o
  WHERE o.order_date BETWEEN :start_date AND :end_date
    AND o.status = 'completed'
    {{AND_FILTERS}}
  GROUP BY DATE_TRUNC('month', o.order_date)
filters:
  store: "o.store_id = :store"
lineage:
  - { table: "orders", column: "customer_id" }
  - { table: "orders", column: "order_date" }
examples:
  - "How many active users did we have last month?"
  - "Monthly active users trend"
  - "MAU by store"
tags:
  - engagement
  - customer
```

**2. Reindex**

```bash
curl -X POST http://localhost:5000/semantic/reindex \
  -H "X-Role: admin"
```

**3. Test in Chat**

Ask: **"How many active users did we have last month?"**

Expected:
> ✨ Using pre-compiled metric: monthly_active_users

---

## DB-Agnostic Setup

### SQLite (Default)

```bash
python scripts/seed_sqlite_retail.py
# Database: data/retail.db
```

In your code, connect:

```python
import sqlite3
conn = sqlite3.connect("data/retail.db")
```

### DuckDB

```bash
pip install duckdb
python scripts/seed_duckdb_retail.py
# Database: data/retail.duckdb
```

```python
import duckdb
conn = duckdb.connect("data/retail.duckdb")
```

### PostgreSQL/MySQL

1. Create tables using DDL from seed scripts
2. Load CSVs via `COPY` (Postgres) or `LOAD DATA` (MySQL)
3. Update `semantic/mdl/entities/*.yaml` to reference correct schema/table names

---

## Benefits

### For Business Users

- **Speak in business terms**: "revenue", "churn", "LTV" instead of SQL
- **Consistent definitions**: Everyone uses the same metric logic
- **Self-service**: No need to know FK relationships or table names

### For Data Teams

- **Centralized logic**: Update metric definition once, affects all queries
- **Governance**: PII masking and row filters enforced automatically
- **Lineage**: Track which tables/columns contribute to each metric

### For Compliance

- **Audit trail**: Provenance shows which policies were applied
- **Role-based access**: `pii_viewer` role required to unmask PII
- **Policy as code**: Masking rules version-controlled in YAML

---

## Troubleshooting

### Semantic Search Not Working

**Symptoms:** Queries don't match metrics even when examples are similar.

**Fix:**

1. Check embedder is loaded:
   ```bash
   GET /semantic/health
   # semantic_index: "available" or "not_indexed"
   ```

2. Rebuild index:
   ```bash
   POST /semantic/reindex (X-Role: admin)
   ```

3. Lower match threshold in `app.py` (line ~1261):
   ```python
   if search_results and search_results[0].get("score", 0) > 0.5:  # was 0.7
   ```

### Compiled SQL Fails

**Symptoms:** Metric compiles but execution fails with SQL error.

**Fix:**

1. Check SQL dialect (T-SQL vs SQLite syntax):
   - SQLite: `DATE(col)` → extract date
   - T-SQL: `CONVERT(DATE, col)` or `CAST(col AS DATE)`

2. Update metric SQL to be dialect-agnostic:
   ```yaml
   sql: |
     SELECT
       strftime('%Y-%m-%d', o.order_date) AS day,  -- SQLite
       -- or CONVERT(DATE, o.order_date) AS day,  -- T-SQL
       ...
   ```

### Relationships Not Showing in UI

**Symptoms:** Modeling page shows empty relationships panel.

**Fix:**

1. Verify YAML files exist:
   ```bash
   ls semantic/mdl/relations/
   ```

2. Check YAML syntax:
   ```bash
   python -c "import yaml; yaml.safe_load(open('semantic/mdl/relations/orders_to_customers.yaml'))"
   ```

3. Reindex:
   ```bash
   POST /semantic/reindex
   ```

---

## Performance Notes

### Semantic Search

- **FAISS index build**: ~1-2 seconds for 50 entities/metrics
- **Search latency**: <50ms for keyword fallback, <100ms with embeddings
- **Embedding generation**: Cached after first load (no per-query cost)

### Metric Compilation

- **Compilation time**: <10ms (template substitution)
- **Execution time**: Depends on query complexity and row count
- **Caching**: Future versions may cache compiled SQL per filter set

---

## Extending the Semantic Layer

### Add New Entity

1. Create `/semantic/mdl/entities/my_entity.yaml`
2. Define columns, grain, tags
3. Reindex: `POST /semantic/reindex`

### Add New Metric

1. Create `/semantic/mdl/metrics/my_metric.yaml`
2. Write templated SQL with placeholders
3. Add examples (used for semantic search)
4. Reindex

### Add New Policy

1. Create `/semantic/mdl/policies/my_policy.yaml`
2. Define type (`mask_column`, `row_filter`, `table_deny`)
3. Specify targets and exempt roles
4. Reindex

---

## Roadmap

### Phase 1 (Current)
- ✅ MDL loader + validator
- ✅ Semantic search (FAISS + keyword)
- ✅ Metric compilation with governance
- ✅ Modeling UI (ERD + relationship CRUD)
- ✅ Planner integration

### Phase 2 (Next)
- ⏳ Auto-extract time range/filters from NL question
- ⏳ Metric versioning (track changes over time)
- ⏳ SQL dialect auto-detection (SQLite vs T-SQL vs Postgres)
- ⏳ Cached compiled SQL for common filter sets

### Phase 3 (Future)
- ⏳ Auto-generate metrics from usage patterns
- ⏳ Semantic lineage graph visualization
- ⏳ Column-level lineage (which source columns → metric)
- ⏳ dbt integration (import dbt models as entities)

---

## FAQ

### Q: Do I need to use the semantic layer?

**A:** No. If no semantic match is found (score < 0.7), the system falls back to standard FAISS retrieval + LLM generation. The semantic layer is optional but improves consistency and speed.

### Q: Can I use this with my existing D365 database?

**A:** Yes. Update the entity YAML files to reference your D365 schema (e.g., `reference: {table: "dbo.CustTable"}`). The semantic layer works with any SQL database.

### Q: How do I handle multiple databases?

**A:** Create separate MDL directories per DB (e.g., `semantic/mdl_d365/`, `semantic/mdl_snowflake/`) and initialize multiple `SemanticEngine` instances. Future versions will support multi-DB routing.

### Q: What if my metric SQL is complex (100+ lines)?

**A:** Break it into smaller reusable metrics. Use CTEs or temp tables in the SQL. For very complex logic, consider creating a database view and referencing it in the metric.

---

## Support

- **Documentation**: This file + `AGENTS.md`
- **Issues**: Check `/docs/CRITICAL_BUGS_FIXED.md` for known issues
- **Contact**: Naveed Shahid (Product Owner)

---

**Happy Modeling!** 🎨📊



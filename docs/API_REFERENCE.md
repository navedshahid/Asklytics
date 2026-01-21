# AskLytics API Reference

Complete documentation for all AskLytics REST API endpoints.

## Table of Contents

- [Authentication & Authorization](#authentication--authorization)
- [Core Query APIs](#core-query-apis)
- [Configuration & Settings](#configuration--settings)
- [Metadata Management](#metadata-management)
- [Learning & Training](#learning--training)
- [Governance & Audit](#governance--audit)
- [Metrics & ROI](#metrics--roi)
- [Feedback](#feedback)
- [Thread Management](#thread-management)
- [Health & Diagnostics](#health--diagnostics)

---

## Authentication & Authorization

### Role-Based Access Control

AskLytics uses role-based access control (RBAC) with roles provided via HTTP headers or secure cookies.

**Supported Roles:**
- `admin` - Full system access
- `auditor` - View audit logs and governance data
- `pii_viewer` - Can unmask PII data with justification
- `security` - Security monitoring and compliance
- `user` (default) - Standard query access with masked PII

**Headers:**
```http
X-Role: admin
X-Roles: auditor,pii_viewer
```

**Cookie:**
```
role=admin
```

**Query Parameters:** NOT SUPPORTED (security risk)

---

## Core Query APIs

### 1. Ask Query (Local LLM)

Generate and execute SQL from natural language using local SQLCoder model.

**Endpoint:** `POST /api/ask/stream`

**Request Headers:**
```http
Content-Type: application/json
X-Role: user
X-Session-ID: uuid-string (optional)
```

**Request Body:**
```json
{
  "question": "What are the top 5 customers by sales?",
  "force_sql": "SELECT * FROM Customers LIMIT 5",
  "unmask": false,
  "pii_reason": "Business analysis for Q4 report"
}
```

**Parameters:**
- `question` (string, required): Natural language question
- `force_sql` (string, optional): Override with explicit SQL
- `unmask` (boolean, optional): Request unmasked PII data (requires `pii_viewer` role)
- `pii_reason` (string, required if unmask=true): Justification for PII access

**Response:** Server-Sent Events (SSE) stream

```
event: sql_complete
data: {"query": "SELECT TOP 5 CustomerName, SUM(Sales) FROM ..."}

event: executing
data: {"message": "Executing SQL query..."}

event: result
data: {"columns": ["CustomerName", "TotalSales"], "data": [...]}

event: explanation
data: {"text": "This query retrieves the top 5 customers..."}

event: summary
data: {"summary": "Found 5 customers", "bullets": ["Average sales: $125K"]}

event: complete
data: {"success": true}
```

**Example (cURL):**
```bash
curl -X POST http://localhost:5000/api/ask/stream \
  -H "Content-Type: application/json" \
  -H "X-Role: user" \
  -H "X-Session-ID: $(uuidgen)" \
  -d '{
    "question": "Show me revenue by region this month"
  }'
```

**Example (Python):**
```python
import requests
import json

url = "http://localhost:5000/api/ask/stream"
headers = {
    "Content-Type": "application/json",
    "X-Role": "user",
    "X-Session-ID": "my-session-123"
}
data = {
    "question": "What are the top products by profit margin?"
}

response = requests.post(url, headers=headers, json=data, stream=True)
for line in response.iter_lines():
    if line.startswith(b'data: '):
        event_data = json.loads(line[6:])
        print(event_data)
```

**Example (JavaScript):**
```javascript
const eventSource = new EventSource('/api/ask/stream?' + new URLSearchParams({
  question: 'Show sales by quarter'
}));

eventSource.addEventListener('result', (event) => {
  const data = JSON.parse(event.data);
  console.log('Results:', data);
});

eventSource.addEventListener('complete', (event) => {
  eventSource.close();
});
```

---

### 2. Ask Query (Gemini)

Generate SQL using Google Gemini with SQLCoder-7B as reviewer/fallback.

**Endpoint:** `POST /api/gemini_ask/stream`

**Request/Response:** Same format as `/api/ask/stream`

**Additional Features:**
- Uses Gemini 1.5 Flash for faster, more accurate SQL generation
- SQLCoder-7B validates and repairs generated SQL
- Automatic fallback to SQLCoder if Gemini unavailable

**Configuration Required:**
```bash
# .env file
GEMINI_API_KEY=your-api-key-here
GEMINI_MODEL_FOR_SQL=gemini-1.5-flash-latest
```

---

### 3. Ask Query (GPT-OSS)

Generate SQL using GPT-OSS-20B model via local vLLM server.

**Endpoint:** `POST /api/gpt_ask/stream`

**Request/Response:** Same format as `/api/ask/stream`

**Configuration Required:**
```json
// asklytics_config.json
{
  "gpt": {
    "base_url": "http://localhost:8000/v1",
    "model": "gpt-oss-20b"
  }
}
```

---

### 4. Query Preview

Preview query intent and refinement without execution.

**Endpoint:** `POST /api/ask/preview`

**Request Body:**
```json
{
  "question": "Show only customers from California"
}
```

**Response:**
```json
{
  "intent": "REFINE_FILTER",
  "will_refine": true,
  "refined_sql": "SELECT * FROM Customers WHERE State = 'CA'"
}
```

**Intent Types:**
- `NEW_QUERY` - Brand new question
- `REFINE_FILTER` - Add/modify WHERE clause
- `REFINE_ADD_COLUMN` - Add columns to SELECT
- `COMPARE` - Compare with previous results
- `AGGREGATE` - Add aggregation (COUNT, SUM, etc.)

---

### 5. Summarize Results

Generate natural language summary of query results.

**Endpoint:** `POST /api/summarize`

**Request:** (uses last session query)

**Response:**
```json
{
  "summary": "The query returned 5 customers with an average revenue of $125,000. The top customer generated $250,000 in sales, while the distribution shows consistent performance across all regions."
}
```

---

## Configuration & Settings

### Database Configuration

#### Get Current DB Config

**Endpoint:** `GET /api/settings/db/current`

**Response:**
```json
{
  "server": "localhost",
  "database": "AdventureWorks",
  "uid": "sa",
  "configured": true
}
```

#### Test DB Connection

**Endpoint:** `POST /api/settings/db/test`

**Request Body:**
```json
{
  "server": "localhost",
  "database": "AdventureWorks",
  "uid": "sa",
  "pwd": "YourPassword123"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Connection successful"
}
```

#### Save DB Configuration

**Endpoint:** `POST /api/settings/db/save`

**Request Body:**
```json
{
  "server": "localhost",
  "database": "AdventureWorks",
  "uid": "sa",
  "pwd": "YourPassword123",
  "driver": "ODBC Driver 17 for SQL Server"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Configuration saved. Pool starting"
}
```

---

### Table Selection

#### List Available Tables

**Endpoint:** `GET /api/settings/tables/list`

**Response:**
```json
{
  "tables": [
    "Sales.SalesOrderHeader",
    "Sales.SalesOrderDetail",
    "Production.Product",
    "HumanResources.Employee"
  ],
  "selected": [
    "Sales.SalesOrderHeader",
    "Production.Product"
  ]
}
```

#### Save Table Selection

**Endpoint:** `POST /api/settings/tables/save`

**Request Body:**
```json
{
  "tables": [
    "Sales.SalesOrderHeader",
    "Production.Product"
  ]
}
```

**Response:**
```json
{
  "status": "success"
}
```

---

### Inference Mode

#### Get Inference Mode

**Endpoint:** `GET /api/settings/inference`

**Response:**
```json
{
  "mode": "gemini",
  "available": ["local", "gemini", "gpt"]
}
```

**Modes:**
- `local` - SQLCoder-7B (local, no API key needed)
- `gemini` - Google Gemini (requires API key)
- `gpt` - GPT-OSS-20B (requires vLLM server)

#### Set Inference Mode

**Endpoint:** `POST /api/settings/inference`

**Request Body:**
```json
{
  "mode": "gemini"
}
```

**Response:**
```json
{
  "status": "success",
  "mode": "gemini"
}
```

---

### Learning Settings

#### Get Learning Config

**Endpoint:** `GET /api/settings/learning`

**Response:**
```json
{
  "auto_log_learning": true,
  "feedback_threshold": 0.7,
  "retrain_interval_hours": 24
}
```

#### Update Learning Config

**Endpoint:** `POST /api/settings/learning`

**Request Body:**
```json
{
  "auto_log_learning": true,
  "feedback_threshold": 0.7
}
```

---

### Governance Settings

#### Get Governance Config

**Endpoint:** `GET /api/settings/governance`

**Response:**
```json
{
  "masking_enabled": true,
  "audit_retention_days": 90,
  "pii_viewer_roles": ["pii_viewer", "auditor", "admin"]
}
```

#### Update Governance Config

**Endpoint:** `POST /api/settings/governance`

**Request Body:**
```json
{
  "masking_enabled": true,
  "audit_retention_days": 90
}
```

---

## Metadata Management

### Harvest Metadata

Extract and store database schema metadata including tables, columns, foreign keys, and descriptions.

**Endpoint:** `POST /api/metadata/harvest`

**Description:**
Connects to your SQL Server database and extracts comprehensive schema metadata. This metadata is used to:
- Enhance SQL generation with FK relationships
- Improve validation with accurate schema info
- Enable semantic search over table descriptions
- Track data lineage

**Request Headers:**
```http
Content-Type: application/json
```

**Request Body:**
```json
{
  "scope": [
    "tables",
    "columns",
    "foreign_keys",
    "views",
    "descriptions",
    "row_counts",
    "samples"
  ],
  "source": "SqlServer:D365"
}
```

**Parameters:**
- `scope` (array, optional): What to harvest. Default: all except samples
  - `tables` - Extract table names and types
  - `columns` - Extract column names, types, lengths
  - `foreign_keys` - Extract FK relationships
  - `views` - Include database views
  - `descriptions` - Extract MS_Description extended properties
  - `row_counts` - Count rows in each table (can be slow)
  - `samples` - Extract top 5 sample values per column (can be slow)
- `source` (string, optional): Source identifier. Default: "SqlServer:D365"

**Response:**
```json
{
  "status": "success",
  "mode": "store_sqlalchemy",
  "assets_upserted": 156
}
```

**Example (cURL):**
```bash
# Basic harvest (fast)
curl -X POST http://localhost:5000/api/metadata/harvest \
  -H "Content-Type: application/json" \
  -d '{
    "scope": ["tables", "columns", "foreign_keys", "descriptions"],
    "source": "SqlServer:MyDatabase"
  }'

# Full harvest with samples (slow but comprehensive)
curl -X POST http://localhost:5000/api/metadata/harvest \
  -H "Content-Type: application/json" \
  -d '{
    "scope": ["tables", "columns", "foreign_keys", "descriptions", "row_counts", "samples"],
    "source": "SqlServer:D365"
  }'
```

**Example (Python):**
```python
import requests

# Harvest schema metadata
response = requests.post(
    "http://localhost:5000/api/metadata/harvest",
    json={
        "scope": ["tables", "columns", "foreign_keys", "descriptions"],
        "source": "SqlServer:Production"
    }
)

result = response.json()
print(f"Harvested {result['assets_upserted']} assets")
```

**What Gets Stored:**

The harvest creates/updates records in `metadata.db`:

**Tables (mm_asset):**
- Kind (Table/View)
- Schema and object names
- Descriptions
- Sensitivity level
- Tags (RowCount, LastModified, etc.)

**Columns (mm_column):**
- Column names and positions
- Data types and lengths
- Nullable flags
- Descriptions with FK hints
- Primary key flags
- Sample values (if requested)

**Relationship Annotations:**
```
Description: "FK->Sales.Customer(CustomerID) | hint:endswithId"
```

**When to Run:**
- ✅ **First-time setup** - Populate metadata database
- ✅ **After schema changes** - Tables/columns added or modified
- ✅ **After deployment** - New database environment
- ✅ **Weekly/monthly** - Keep descriptions and stats fresh

**Performance Notes:**
- Basic harvest (without samples/counts): 5-30 seconds for 100 tables
- With row counts: +1-5 seconds per table
- With samples: +2-10 seconds per table
- Runs asynchronously - won't block other requests

---

### List Database Tables (Semantic Bootstrap)

Retrieve live database schema details (tables + columns) that can be converted into MDL entities.

**Endpoint:** `GET /semantic/db/tables`

**Authorization:** Any authenticated role; requires database connection to be configured.

**Response:**
```json
{
  "tables": [
    {
      "name": "Customers",
      "schema": "dbo",
      "full_name": "[dbo].[Customers]",
      "qualified_name": "dbo.Customers",
      "columns": [
        {"name": "CustomerId", "dtype": "integer", "primary": true, "nullable": false},
        {"name": "Email", "dtype": "string", "nullable": true, "description": "varchar(200)"}
      ]
    }
  ]
}
```

Each column entry includes the semantic data type, source type description, ordinal position, and whether it is nullable or part of the primary key. This payload mirrors what the UI builder uses when composing MDL entity files.

---

### Bulk Import Entities into Semantic MDL

Generate MDL entity YAML files directly from selected database tables.

**Endpoint:** `POST /semantic/entities/import`

**Authorization:** `admin` role (writes YAML files under `semantic/mdl/entities`).

**Request Body:**
```json
{
  "tables": ["dbo.Customers", {"schema": "dbo", "table": "Orders"}],
  "dry_run": false,
  "detect_pii": true,
  "name_prefix": "mdl_",
  "tags": ["retail", "auto"],
  "name_overrides": {
    "dbo.Customers": "customer_master"
  }
}
```

- `tables` (array, required): List of table identifiers to convert. Accepts strings (`schema.table`, `[schema].[table]`, or `table`) or objects `{ "schema": "...", "table": "..." }`.
- `dry_run` (bool, default `false`): When `true`, returns generated documents without writing to disk.
- `detect_pii` (bool, default `true`): Applies name-based heuristics to flag likely PII columns.
- `name_prefix` (string, optional): Prepends a prefix to every generated entity name.
- `tags` (array, optional): Additional tags appended to each entity’s `tags` list.
- `name_overrides` (object, optional): Mapping of `schema.table` (or table) → desired entity name.

**Response (dry_run=false):**
```json
{
  "status": "success",
  "dry_run": false,
  "count": 2,
  "entities": [
    {"table": "dbo.Customers", "name": "mdl_customer_master", "path": "semantic/mdl/entities/mdl_customer_master.yaml"},
    {"table": "dbo.Orders", "name": "mdl_orders", "path": "semantic/mdl/entities/mdl_orders.yaml"}
  ],
  "errors": []
}
```

When `dry_run=true`, the `entities` array contains the full entity payload (`name`, `grain`, `columns`, `properties`, etc.) so you can preview the YAML that would be written.

**PII Detection:** Columns whose names contain keywords like `email`, `phone`, `first_name`, etc., are automatically marked with `pii: true` (string-like columns only). You can still edit the resulting YAML to fine-tune tags or descriptions.

---

### Metadata Health Check

Check metadata system status.

**Endpoint:** `GET /api/metadata/health`

**Response:**
```json
{
  "routes_loaded": true,
  "store_loaded": true,
  "orch_loaded": true,
  "db_url": "sqlite:///./metadata.db",
  "sqlite_path": "./metadata.db",
  "sqlite_exists": true
}
```

---

### Search Metadata Assets

Search for tables and views by name or description.

**Endpoint:** `GET /api/metadata/assets`

**Query Parameters:**
- `q` (string, optional): Search query
- `limit` (integer, optional): Max results. Default: 25

**Response:**
```json
{
  "results": [
    {
      "AssetId": 123,
      "Kind": "Table",
      "Key": "SqlServer:Sales.Orders",
      "DisplayName": "Orders",
      "Description": "Sales order transactions",
      "Sensitivity": "Internal",
      "UpdatedAt": "2025-10-30T15:30:00Z",
      "Tags": ["harvested", "RowCount=15623"]
    }
  ]
}
```

**Example:**
```bash
# Search for customer-related tables
curl "http://localhost:5000/api/metadata/assets?q=customer&limit=10"
```

---

### Get Asset Detail

Retrieve detailed metadata for a specific table.

**Endpoint:** `GET /api/metadata/assets/<asset_id>`

**Response:**
```json
{
  "Asset": {
    "AssetId": 123,
    "Kind": "Table",
    "Key": "SqlServer:Sales.Orders",
    "DisplayName": "Orders",
    "Description": "Sales order transactions",
    "OwnerEmail": null,
    "Sensitivity": "Internal",
    "Version": 3,
    "UpdatedAt": "2025-10-30T15:30:00Z",
    "Tags": ["harvested", "RowCount=15623"]
  },
  "Columns": [
    {
      "ColumnName": "OrderID",
      "OrdinalPos": 1,
      "DataType": "int",
      "MaxLength": null,
      "IsNullable": false,
      "Description": "PK | hint:endswithId"
    },
    {
      "ColumnName": "CustomerID",
      "OrdinalPos": 2,
      "DataType": "int",
      "MaxLength": null,
      "IsNullable": false,
      "Description": "FK->Sales.Customer(CustomerID) | hint:endswithId"
    }
  ]
}
```

---

### Export Business Knowledge Graph

Export complete schema as a business knowledge graph.

**Endpoint:** `GET /api/metadata/bkg`

**Description:**
Exports all metadata in a structured format suitable for visualization, documentation, or integration with other tools.

**Response:**
```json
{
  "version": 1,
  "entities": [
    {
      "id": 123,
      "key": "SqlServer:Sales.Orders",
      "source": "SqlServer",
      "schema": "Sales",
      "table": "Orders",
      "name": "Orders",
      "description": "Sales order transactions",
      "domain": "Sales",
      "tags": ["harvested"]
    }
  ],
  "attributes": {
    "SqlServer:Sales.Orders": [
      {
        "name": "OrderID",
        "type": "int",
        "nullable": false,
        "is_key": true,
        "description": "PK"
      }
    ]
  },
  "relationships": [
    {
      "from": {
        "entity": "SqlServer:Sales.Orders",
        "column": "CustomerID"
      },
      "to": {
        "entity": "SqlServer:Sales.Customer",
        "column": "CustomerID"
      },
      "type": "fk",
      "confidence": 1.0
    }
  ],
  "synonyms": [
    {"terms": ["Store", "Site", "Outlet"]},
    {"terms": ["Item", "SKU", "Article"]}
  ],
  "kpis": []
}
```

**Use Cases:**
- Generate ER diagrams
- Create data dictionaries
- Export to documentation tools
- Analyze data lineage
- Build data catalogs

---

## Learning & Training

### Submit Training Example

Add verified query/SQL pairs to improve the model.

**Endpoint:** `POST /api/training/run`

**Request Body:**
```json
{
  "prompt": "Show sales by region",
  "sql": "SELECT Region, SUM(Sales) FROM Orders GROUP BY Region",
  "score": 1.0
}
```

**Response:**
```json
{
  "status": "success",
  "xp_id": 123
}
```

---

### Reload FAISS Index

Rebuild the vector index from verified examples.

**Endpoint:** `POST /api/faiss/reload`

**Response:**
```json
{
  "status": "success",
  "indexed_count": 156,
  "duration_ms": 234
}
```

---

### Run Regression Suite

Execute all regression tests to validate model performance.

**Endpoint:** `POST /api/learn/regression/run`

**Response:**
```json
{
  "summary": {
    "passed": 45,
    "failed": 2,
    "duration_ms": 5670
  },
  "results": [
    {
      "prompt": "Show top customers",
      "expected_sql": "SELECT TOP 10...",
      "actual_sql": "SELECT TOP 10...",
      "passed": true
    }
  ]
}
```

---

### Validate SQL

Validate SQL against schema and business rules.

**Endpoint:** `POST /api/learn/validate`

**Request Body:**
```json
{
  "sql": "SELECT * FROM Customers WHERE Region = 'West'",
  "prompt": "Show western customers"
}
```

**Response:**
```json
{
  "valid": true,
  "confidence_score": 0.92,
  "confidence_label": "High",
  "warnings": [],
  "errors": [],
  "signals": {
    "tables_used": ["Customers"],
    "fk_ok": true,
    "group_by_ok": true
  }
}
```

---

### Cleanup Old Data

Remove old experiences and optimize database.

**Endpoint:** `POST /api/learn/cleanup`

**Request Body:**
```json
{
  "days": 90
}
```

**Response:**
```json
{
  "status": "success",
  "removed": 234,
  "space_freed_mb": 12.5
}
```

---

### Reset Learning Data

Clear all learning data (requires admin role).

**Endpoint:** `POST /api/learn/reset`

**Response:**
```json
{
  "status": "success",
  "message": "Learning data reset complete"
}
```

---

## Governance & Audit

### Audit Rollup

Get aggregated audit metrics for dashboards.

**Endpoint:** `GET /api/gov/audit/rollup`

**Query Parameters:**
- `days` (integer, default: 30): Time window in days

**Response:**
```json
{
  "window_days": 30,
  "events": 1523,
  "actions": [
    {"action": "sql_executed", "count": 856},
    {"action": "prompt_submitted", "count": 432},
    {"action": "pii_exposure", "count": 12}
  ],
  "pii_exposures": 12,
  "total_cost_estimate": 4.56,
  "last_event_utc": "2025-10-30T15:30:00Z"
}
```

---

### Audit Events

Retrieve recent audit events (masked).

**Endpoint:** `GET /api/gov/audit/events`

**Query Parameters:**
- `limit` (integer, default: 50, max: 200): Number of events

**Response:**
```json
{
  "events": [
    {
      "ts_utc": "2025-10-30T15:30:00Z",
      "user_hash": "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3",
      "action": "sql_executed",
      "resource": "xp_123",
      "masked": 1,
      "meta": "{\"confidence\": 0.92}"
    }
  ]
}
```

---

### Export Audit Log

Export audit logs as CSV (requires auditor role).

**Endpoint:** `GET /api/audit/export`

**Query Parameters:**
- `days` (integer, default: 30): Days of history to export

**Response:** CSV file download

```csv
ts_utc,provider,prompt_hash,sql_hash,feedback,exec_time_ms,token_cost_estimate
2025-10-30T15:30:00Z,gemini,abc123...,def456...,positive,234,0.00012
```

---

## Metrics & ROI

### Average Confidence

Get average confidence score over time window.

**Endpoint:** `GET /api/metrics/avg_confidence`

**Query Parameters:**
- `days` (integer, default: 30)

**Response:**
```json
{
  "avg_confidence": 0.847,
  "window_days": 30,
  "sample_size": 523
}
```

---

### Confidence Trend

Get weekly confidence trend.

**Endpoint:** `GET /api/metrics/confidence_trend`

**Query Parameters:**
- `weeks` (integer, default: 8)

**Response:**
```json
{
  "trend": [
    {"week_start": "2025-09-01", "avg_confidence": 0.82},
    {"week_start": "2025-09-08", "avg_confidence": 0.85},
    {"week_start": "2025-09-15", "avg_confidence": 0.87}
  ]
}
```

---

### Accuracy KPI

Get percentage of high-confidence queries.

**Endpoint:** `GET /api/metrics/accuracy_kpi`

**Query Parameters:**
- `threshold` (float, default: 0.8): Confidence threshold
- `days` (integer, default: 30)

**Response:**
```json
{
  "accuracy": 0.892,
  "threshold": 0.8,
  "window_days": 30,
  "total_queries": 523,
  "high_confidence": 466
}
```

---

### Feedback Trend

Get daily feedback accuracy trend.

**Endpoint:** `GET /api/roi/feedback_trend`

**Query Parameters:**
- `days` (integer, default: 30)

**Response:**
```json
{
  "trend": [
    {"date": "2025-10-01", "accuracy": 0.89, "total": 23},
    {"date": "2025-10-02", "accuracy": 0.92, "total": 18}
  ]
}
```

---

## Feedback

### Submit Feedback

Submit user feedback on query results.

**Endpoint:** `POST /api/feedback`

**Request Body:**
```json
{
  "xp_id": 123,
  "verdict": "correct",
  "comment": "Perfect query, got exactly what I needed",
  "confidence": 0.95
}
```

**Parameters:**
- `xp_id` (integer, required): Experience ID from query execution
- `verdict` (string, required): "correct" or "incorrect"
- `comment` (string, optional): User comments
- `confidence` (float, optional): User-perceived confidence (0-1)

**Response:**
```json
{
  "status": "success",
  "feedback_id": 456,
  "indexed": true
}
```

---

### Feedback Summary

Get feedback statistics.

**Endpoint:** `GET /api/feedback/summary`

**Query Parameters:**
- `days` (integer, default: 30)

**Response:**
```json
{
  "total": 234,
  "correct": 212,
  "incorrect": 22,
  "accuracy": 0.906
}
```

---

### List Feedback

Get detailed feedback list (requires auditor role).

**Endpoint:** `GET /api/feedback/list`

**Query Parameters:**
- `limit` (integer, default: 50)

**Response:**
```json
{
  "results": [
    {
      "id": 456,
      "ts": "2025-10-30T15:30:00Z",
      "xp_id": 123,
      "user_id": "hashed_user_id",
      "verdict": "correct",
      "comment": "Perfect query",
      "confidence": 0.95,
      "masked": true,
      "retrain_used": true
    }
  ]
}
```

---

## Thread Management

### List Threads

Get all conversation threads for current user.

**Endpoint:** `GET /api/threads`

**Response:**
```json
{
  "threads": [
    {
      "id": "thread-123",
      "title": "Q4 Sales Analysis",
      "created": "2025-10-30T10:00:00Z",
      "updated": "2025-10-30T15:30:00Z",
      "message_count": 5
    }
  ]
}
```

---

### Create Thread

Create a new conversation thread.

**Endpoint:** `POST /api/threads`

**Request Body:**
```json
{
  "title": "Q4 Sales Analysis"
}
```

**Response:**
```json
{
  "id": "thread-123",
  "title": "Q4 Sales Analysis",
  "created": "2025-10-30T15:30:00Z"
}
```

---

### Get Thread

Retrieve a specific thread with all messages.

**Endpoint:** `GET /api/threads/<tid>`

**Response:**
```json
{
  "id": "thread-123",
  "title": "Q4 Sales Analysis",
  "messages": [
    {
      "role": "user",
      "content": "Show sales by region"
    },
    {
      "role": "assistant",
      "content": "Here are the results...",
      "sql": "SELECT Region, SUM(Sales)...",
      "data": [...]
    }
  ]
}
```

---

### Rename Thread

Update thread title.

**Endpoint:** `POST /api/threads/<tid>/rename`

**Request Body:**
```json
{
  "title": "Q4 2025 Sales Analysis - Final"
}
```

---

### Add Message

Add a message to an existing thread.

**Endpoint:** `POST /api/threads/<tid>/messages`

**Request Body:**
```json
{
  "question": "Now show only top 10"
}
```

**Response:** Same as query API (SSE stream)

---

### Delete Thread

Remove a thread and all its messages.

**Endpoint:** `DELETE /api/threads/<tid>`

**Response:**
```json
{
  "status": "success"
}
```

---

## Health & Diagnostics

### System Status

Get high-level system status.

**Endpoint:** `GET /api/status`

**Response:**
```json
{
  "status": "healthy",
  "db_configured": true,
  "models_loaded": true,
  "inference_mode": "gemini"
}
```

---

### Full Health Check

Comprehensive health check with component status.

**Endpoint:** `GET /api/health/full`

**Response:**
```json
{
  "status": "healthy",
  "components": {
    "database": {
      "status": "healthy",
      "connection_pool_size": 5,
      "active_connections": 2
    },
    "models": {
      "status": "healthy",
      "llm_loaded": true,
      "embedder_loaded": true,
      "faiss_index_size": 1523
    },
    "learning": {
      "status": "healthy",
      "xp_count": 5234,
      "feedback_count": 523
    }
  },
  "uptime_seconds": 86400,
  "version": "1.0.0"
}
```

---

### Diagnostics

Get detailed system diagnostics.

**Endpoint:** `GET /api/diagnostics`

**Response:**
```json
{
  "db": {
    "configured": true,
    "server": "localhost",
    "database": "AdventureWorks"
  },
  "models": {
    "llm": "sqlcoder-7b-2",
    "embedder": "BAAI/bge-m3",
    "gpu_layers": 0
  },
  "faiss": {
    "indexed_count": 1523,
    "index_size_mb": 45.2
  },
  "system": {
    "python_version": "3.11.5",
    "platform": "Windows-10",
    "memory_mb": 16384
  }
}
```

---

### Reload Models

Hot-reload LLM and embedder models.

**Endpoint:** `POST /api/models/reload`

**Response:**
```json
{
  "status": "success",
  "llm_loaded": true,
  "embedder_loaded": true,
  "load_time_ms": 2341
}
```

---

## Error Handling

All API endpoints follow a consistent error format:

```json
{
  "ok": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "SQL validation failed: table 'xyz' not found"
  }
}
```

**Common Error Codes:**
- `VALIDATION_ERROR` - SQL validation failed
- `AUTHENTICATION_ERROR` - Missing or invalid credentials
- `AUTHORIZATION_ERROR` - Insufficient permissions
- `DATABASE_ERROR` - Database connection or query error
- `MODEL_ERROR` - LLM model error
- `RATE_LIMIT_ERROR` - Too many requests
- `INTERNAL_ERROR` - Unexpected server error

**HTTP Status Codes:**
- `200` - Success
- `400` - Bad request (invalid parameters)
- `401` - Unauthorized (authentication required)
- `403` - Forbidden (insufficient permissions)
- `404` - Not found
- `429` - Too many requests
- `500` - Internal server error

---

## Rate Limiting

**Default Limits:**
- 100 requests per minute per user
- 5 concurrent sessions per user
- Max query execution time: 30 seconds

**Headers:**
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1698765432
```

---

## Best Practices

### 1. Session Management

Always use consistent `X-Session-ID` headers to maintain conversation context:

```python
import uuid

session_id = str(uuid.uuid4())
headers = {"X-Session-ID": session_id}

# All requests in the same conversation use the same session_id
```

### 2. PII Handling

Only request unmasked PII when absolutely necessary:

```python
# Good - masked by default
response = ask_query("Show customers", unmask=False)

# Only when needed
response = ask_query(
    "Show customers with contact details",
    unmask=True,
    pii_reason="Customer outreach for Q4 campaign - approved by CMO"
)
```

### 3. Error Handling

Always handle streaming errors gracefully:

```javascript
eventSource.addEventListener('error', (event) => {
  if (event.data) {
    const error = JSON.parse(event.data);
    console.error('Query failed:', error.message);
  }
  eventSource.close();
});
```

### 4. Feedback Loop

Submit feedback to improve results:

```python
# After viewing results
submit_feedback(
    xp_id=response.xp_id,
    verdict="correct",
    confidence=0.95,
    comment="Perfect results"
)
```

---

## SDK Examples

### Python SDK

```python
class AskLyticsClient:
    def __init__(self, base_url, role="user"):
        self.base_url = base_url
        self.role = role
        self.session_id = str(uuid.uuid4())
    
    def ask(self, question, unmask=False, pii_reason=None):
        headers = {
            "Content-Type": "application/json",
            "X-Role": self.role,
            "X-Session-ID": self.session_id
        }
        data = {"question": question}
        if unmask:
            data["unmask"] = True
            data["pii_reason"] = pii_reason
        
        response = requests.post(
            f"{self.base_url}/api/gemini_ask/stream",
            headers=headers,
            json=data,
            stream=True
        )
        
        results = {}
        for line in response.iter_lines():
            if line.startswith(b'event: '):
                event_type = line[7:].decode()
            elif line.startswith(b'data: '):
                data = json.loads(line[6:])
                results[event_type] = data
        
        return results

# Usage
client = AskLyticsClient("http://localhost:5000")
results = client.ask("Show sales by region")
print(results['result']['data'])
```

---

## Postman Collection

Import the Postman collection for interactive API testing:

```json
{
  "info": {
    "name": "AskLytics API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Ask Query (Gemini)",
      "request": {
        "method": "POST",
        "header": [
          {"key": "Content-Type", "value": "application/json"},
          {"key": "X-Role", "value": "user"}
        ],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"question\": \"Show sales by region\"\n}"
        },
        "url": "{{baseUrl}}/api/gemini_ask/stream"
      }
    }
  ],
  "variable": [
    {"key": "baseUrl", "value": "http://localhost:5000"}
  ]
}
```

---

## Support

- **Documentation:** https://github.com/your-org/asklytics/docs
- **Issues:** https://github.com/your-org/asklytics/issues
- **Email:** support@asklytics.com

---

*Last Updated: October 30, 2025*
*API Version: 1.0.0*

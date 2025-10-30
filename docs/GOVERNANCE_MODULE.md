# Governance Module Documentation

Complete documentation for AskLytics governance, security, and compliance features.

## Table of Contents

- [Overview](#overview)
- [RBAC (Role-Based Access Control)](#rbac-role-based-access-control)
- [PII Masking](#pii-masking)
- [Audit Logging](#audit-logging)
- [Compliance Features](#compliance-features)
- [Security Best Practices](#security-best-practices)

---

## Overview

The governance module provides ISO 27001-aligned security controls for:
- Role-based access control (RBAC)
- Automatic PII masking with controlled unmasking
- Comprehensive audit logging
- Compliance reporting and dashboards

### Key Principles

1. **Mask by Default**: All PII is masked unless explicitly unmasked with justification
2. **Least Privilege**: Users have minimum necessary permissions
3. **Audit Everything**: All security-relevant actions are logged
4. **Defense in Depth**: Multiple layers of security controls

---

## RBAC (Role-Based Access Control)

### Module: `governance/rbac.py`

### Supported Roles

```python
# governance/rbac.py
PII_VIEWER_ROLES = {"pii_viewer", "auditor", "admin", "security"}
```

| Role | Permissions |
|------|-------------|
| `user` | Execute queries, view masked data |
| `pii_viewer` | Unmask PII with justification |
| `auditor` | View audit logs, governance dashboard |
| `admin` | Full system access |
| `security` | Security monitoring, compliance reports |

### API Functions

#### `resolve_roles(request: Request) -> Set[str]`

Resolves user roles from HTTP headers and secure cookies.

**Parameters:**
- `request` (Flask Request): The HTTP request object

**Returns:**
- Set of role strings

**Sources (in order):**
1. `X-Role` header (single role)
2. `X-Roles` header (comma-separated roles)
3. `role` cookie (comma or semicolon separated)

**Security Note:** Query parameters are NOT accepted to prevent privilege escalation attacks.

**Example:**
```python
from flask import request
from governance import resolve_roles

@app.route("/api/sensitive")
def sensitive_endpoint():
    roles = resolve_roles(request)
    if "admin" not in roles:
        return jsonify({"error": "Forbidden"}), 403
    # ... admin logic
```

---

#### `can_view_pii(roles: Iterable[str]) -> bool`

Checks if user has permission to view unmasked PII.

**Parameters:**
- `roles` (Iterable[str]): User's roles

**Returns:**
- `True` if user can view PII, `False` otherwise

**Example:**
```python
from governance import resolve_roles, can_view_pii

roles = resolve_roles(request)
unmask_requested = request.json.get("unmask", False)

if unmask_requested and not can_view_pii(roles):
    return jsonify({"error": "PII access denied"}), 403
```

---

### Usage Patterns

#### Basic Authorization Check

```python
from governance import resolve_roles

@app.route("/api/admin/settings")
def admin_settings():
    roles = resolve_roles(request)
    if "admin" not in roles:
        return jsonify({"error": "Admin role required"}), 403
    
    # Admin logic here
    return jsonify({"settings": get_settings()})
```

---

#### PII Access with Justification

```python
from governance import resolve_roles, can_view_pii

@app.route("/api/customer/details")
def customer_details():
    roles = resolve_roles(request)
    unmask = request.json.get("unmask", False)
    pii_reason = request.json.get("pii_reason", "")
    
    # Validate PII access request
    if unmask:
        if not can_view_pii(roles):
            return jsonify({"error": "PII access denied for your roles"}), 403
        
        if not pii_reason:
            return jsonify({"error": "pii_reason is required for unmasking"}), 400
        
        # Log PII access
        audit_logger.log_event(
            root=APP_ROOT,
            user_id=get_user_id(),
            action="pii_exposure",
            resource=f"customer_{customer_id}",
            masked=False,
            meta={"reason": pii_reason}
        )
    
    # Fetch and mask/unmask data
    data = get_customer_data(customer_id)
    if not unmask:
        data = mask_customer_data(data)
    
    return jsonify(data)
```

---

#### Multi-Role Authorization

```python
from governance import resolve_roles

@app.route("/api/feedback/list")
def feedback_list():
    roles = resolve_roles(request)
    
    # Allow both auditor and admin roles
    if "auditor" not in roles and "admin" not in roles:
        return jsonify({
            "error": "forbidden",
            "message": "Auditor or admin role required"
        }), 403
    
    return jsonify(get_feedback_list())
```

---

## PII Masking

### Module: `governance/masker.py`

### MaskingPolicy Class

```python
@dataclass
class MaskingPolicy:
    pii_columns: Mapping[str, Iterable[str]] | None = None
    mask_token: str = "***"
    preserve_nulls: bool = True
    additional_keywords: Set[str] = field(default_factory=set)
```

**Attributes:**
- `pii_columns`: Map of table names to PII column names
- `mask_token`: Token used for masking (default: "***")
- `preserve_nulls`: Keep NULL values as NULL (default: True)
- `additional_keywords`: Additional keywords to trigger masking

---

### Default PII Keywords

The masker automatically identifies and masks columns containing these keywords:

```python
_SENSITIVE_KEYWORDS = {
    "name", "first_name", "last_name", "fullname",
    "email", "phone", "mobile",
    "ssn", "tax", "passport",
    "dob", "birth",
    "address", "street", "city", "zip", "postal",
    "iban", "account", "card"
}
```

---

### Masking Functions

#### `mask_row()`

Mask a single row of data.

```python
def mask_row(
    row: Mapping[str, Any],
    columns: Sequence[str] | Sequence[Mapping[str, Any]] | None,
    policy: MaskingPolicy,
    *,
    tables: Sequence[str] | None = None,
    expose: bool = False,
) -> Dict[str, Any]:
```

**Parameters:**
- `row`: Dictionary of column names to values
- `columns`: List of column names or metadata
- `policy`: MaskingPolicy instance
- `tables`: Optional table names for context-aware masking
- `expose`: If True, returns unmasked data (privileged path)

**Returns:**
- Masked copy of the row

**Example:**
```python
from governance import MaskingPolicy, mask_row

# Define PII columns
policy = MaskingPolicy(
    pii_columns={
        "Customers": ["CustomerName", "Email", "Phone"],
        "Employees": ["FirstName", "LastName", "SSN"]
    }
)

# Mask a row
raw_row = {
    "CustomerID": 123,
    "CustomerName": "John Doe",
    "Email": "john@example.com",
    "Revenue": 50000
}

masked = mask_row(
    row=raw_row,
    columns=["CustomerID", "CustomerName", "Email", "Revenue"],
    policy=policy,
    tables=["Customers"]
)

# Result:
# {
#     "CustomerID": 123,
#     "CustomerName": "Jo***oe",
#     "Email": "jo***om",
#     "Revenue": 50000
# }
```

---

#### `mask_rows()`

Mask multiple rows efficiently.

```python
def mask_rows(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str] | Sequence[Mapping[str, Any]] | None,
    policy: MaskingPolicy,
    *,
    tables: Sequence[str] | None = None,
    expose: bool = False,
) -> list[Dict[str, Any]]:
```

**Example:**
```python
from governance import MaskingPolicy, mask_rows

policy = MaskingPolicy(pii_columns={"Customers": ["Email"]})

raw_rows = [
    {"ID": 1, "Email": "alice@example.com"},
    {"ID": 2, "Email": "bob@example.com"}
]

masked = mask_rows(
    rows=raw_rows,
    columns=["ID", "Email"],
    policy=policy,
    tables=["Customers"]
)

# Result: Email addresses are masked
```

---

### Masking Behavior

#### String Masking

- **Short strings (≤4 chars)**: Fully masked → `"***"`
- **Long strings**: First 2 + last 2 chars visible → `"Jo***oe"`
- **Empty strings**: Unchanged → `""`

```python
policy.mask_value("John Doe")      # "Jo***oe"
policy.mask_value("john@ex.com")   # "jo***om"
policy.mask_value("ABC")           # "***"
policy.mask_value("")              # ""
```

---

#### Numeric Masking

Numbers are fully masked:

```python
policy.mask_value(123456)    # "***"
policy.mask_value(99.99)     # "***"
```

---

#### NULL Handling

```python
policy = MaskingPolicy(preserve_nulls=True)
policy.mask_value(None)  # None

policy = MaskingPolicy(preserve_nulls=False)
policy.mask_value(None)  # "***"
```

---

### Custom Masking Policies

#### Table-Specific PII

```python
policy = MaskingPolicy(
    pii_columns={
        "Customers": ["CustomerName", "Email", "Phone"],
        "Employees": ["FirstName", "LastName", "SSN", "Salary"],
        "Orders": []  # No PII in Orders table
    }
)
```

---

#### Global PII Columns

Use empty string key for table-agnostic masking:

```python
policy = MaskingPolicy(
    pii_columns={
        "": ["email", "phone", "ssn"]  # Mask these columns in ANY table
    }
)
```

---

#### Additional Keywords

```python
policy = MaskingPolicy(
    additional_keywords={"internal_notes", "comments", "remarks"}
)

# Now these columns will also be masked
```

---

#### Custom Mask Token

```python
policy = MaskingPolicy(mask_token="[REDACTED]")

policy.mask_value("sensitive")  # "se[REDACTED]ve"
```

---

### Integration Example

Complete example with database query:

```python
from flask import Flask, request, jsonify
from governance import MaskingPolicy, mask_rows, resolve_roles, can_view_pii

app = Flask(__name__)

# Define masking policy
POLICY = MaskingPolicy(
    pii_columns={
        "Sales.Customer": ["CustomerName", "EmailAddress", "Phone"],
        "HumanResources.Employee": ["FirstName", "LastName", "SSN"]
    }
)

@app.route("/api/customers")
def get_customers():
    # Check authorization
    roles = resolve_roles(request)
    unmask = request.args.get("unmask") == "true"
    pii_reason = request.args.get("pii_reason", "")
    
    # Validate PII access
    expose_pii = False
    if unmask:
        if not can_view_pii(roles):
            return jsonify({"error": "PII access denied"}), 403
        if not pii_reason:
            return jsonify({"error": "pii_reason required"}), 400
        expose_pii = True
    
    # Execute query
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT CustomerID, CustomerName, EmailAddress FROM Sales.Customer")
        columns = [col[0] for col in cursor.description]
        raw_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    # Mask data unless authorized
    masked_rows = mask_rows(
        rows=raw_rows,
        columns=columns,
        policy=POLICY,
        tables=["Sales.Customer"],
        expose=expose_pii
    )
    
    # Audit PII exposure
    if expose_pii:
        audit_logger.log_event(
            root=APP_ROOT,
            user_id=get_user_id(),
            action="pii_exposure",
            resource="Sales.Customer",
            masked=False,
            meta={"reason": pii_reason, "row_count": len(masked_rows)}
        )
    
    return jsonify({
        "columns": columns,
        "data": masked_rows,
        "masked": not expose_pii
    })
```

---

## Audit Logging

### Module: `audit_logger.py`

### Functions

#### `log_interaction()`

Log LLM query interactions.

```python
def log_interaction(
    root: Path,
    provider: str,
    prompt: str,
    sql: str,
    feedback: str,
    exec_time_ms: int
) -> None:
```

**Example:**
```python
import audit_logger
from pathlib import Path

audit_logger.log_interaction(
    root=Path("."),
    provider="gemini",
    prompt="Show sales by region",
    sql="SELECT Region, SUM(Sales) FROM Orders GROUP BY Region",
    feedback="correct",
    exec_time_ms=234
)
```

---

#### `log_event()`

Log generic governance events.

```python
def log_event(
    root: Path | None,
    *,
    user_id: str,
    action: str,
    resource: str = "",
    masked: bool = True,
    meta: dict | None = None
) -> None:
```

**Actions:**
- `prompt_submitted` - User asked a question
- `sql_generated` - LLM generated SQL
- `sql_executed` - SQL executed successfully
- `validation_complete` - SQL validation finished
- `pii_exposure` - PII data was unmasked
- `feedback_submit` - User submitted feedback
- `export_csv` - Data exported to CSV
- `config_change` - System configuration changed

**Example:**
```python
audit_logger.log_event(
    root=APP_ROOT,
    user_id="user@example.com",
    action="pii_exposure",
    resource="customer_12345",
    masked=False,
    meta={
        "reason": "Q4 sales campaign",
        "approved_by": "manager@example.com"
    }
)
```

---

#### `log_validation_summary()`

Log SQL validation results.

```python
audit_logger.log_validation_summary(
    root=APP_ROOT,
    score=0.92,
    label="High",
    semantic_conf=0.89
)
```

---

#### `export_last_30_days_csv()`

Export audit logs to CSV.

```python
from pathlib import Path

csv_path = audit_logger.export_last_30_days_csv(
    root=APP_ROOT,
    out_file=Path("data/audit_export.csv")
)
print(f"Audit log exported to: {csv_path}")
```

---

### Audit Tables

#### `audit_log` - LLM Interactions

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    provider TEXT,              -- "gemini", "local", etc.
    prompt_hash TEXT,           -- SHA1 hash of scrubbed prompt
    sql_hash TEXT,              -- SHA1 hash of scrubbed SQL
    feedback TEXT,              -- "correct", "incorrect"
    exec_time_ms INTEGER,
    token_cost_estimate REAL
);
```

---

#### `audit_events` - Governance Events

```sql
CREATE TABLE audit_events (
    id INTEGER PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    user_hash TEXT,             -- SHA1 hash of user ID
    action TEXT NOT NULL,       -- "pii_exposure", "sql_executed", etc.
    resource TEXT,              -- Resource identifier
    masked INTEGER DEFAULT 1,  -- 0 if PII was exposed
    meta TEXT                   -- JSON metadata
);
```

---

#### `audit_validation` - Validation Events

```sql
CREATE TABLE audit_validation (
    id INTEGER PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    action TEXT NOT NULL,       -- "validation_complete"
    score REAL,                 -- Confidence score
    label TEXT,                 -- "High", "Medium", "Low"
    semantic_conf REAL          -- Semantic validation confidence
);
```

---

## Compliance Features

### ISO 27001 Alignment

The governance module supports ISO 27001 requirements:

| Control | Implementation |
|---------|---------------|
| A.9 Access Control | RBAC with role-based permissions |
| A.12.4 Logging | Comprehensive audit logging |
| A.18.1 Privacy | PII masking by default |
| A.12.3 Backup | Audit log retention and export |

---

### GDPR Compliance

| Requirement | Implementation |
|-------------|---------------|
| Right to Privacy | PII masked by default |
| Lawful Basis | PII access requires justification |
| Audit Trail | All PII access logged with reason |
| Data Minimization | Only authorized roles can unmask |

---

### SOC 2 Type II

| Trust Principle | Implementation |
|-----------------|---------------|
| Security | Multi-layer authorization |
| Availability | Health checks and monitoring |
| Confidentiality | PII masking and encryption |
| Privacy | User data hashing |
| Processing Integrity | SQL validation and audit |

---

## Security Best Practices

### 1. Never Trust User Input

```python
# BAD - Using user input directly
role = request.args.get("role")  # User-controlled!

# GOOD - Use centralized role resolution
roles = resolve_roles(request)
```

---

### 2. Always Validate PII Access

```python
# BAD - No validation
if request.json.get("unmask"):
    expose_pii = True

# GOOD - Validate role and require justification
if request.json.get("unmask"):
    roles = resolve_roles(request)
    if not can_view_pii(roles):
        return error(403, "PII access denied")
    if not request.json.get("pii_reason"):
        return error(400, "pii_reason required")
    expose_pii = True
```

---

### 3. Log All Security Events

```python
# Always log PII exposure
if expose_pii:
    audit_logger.log_event(
        root=APP_ROOT,
        user_id=user_id,
        action="pii_exposure",
        resource=resource_id,
        masked=False,
        meta={"reason": pii_reason}
    )
```

---

### 4. Use Context Managers for Resources

```python
# GOOD - Automatic cleanup
with get_db_connection() as conn:
    cursor = conn.cursor()
    # ... execute query

# Connection automatically closed even on exception
```

---

### 5. Hash Sensitive Data in Logs

```python
import hashlib

def hash_user_id(user_id: str) -> str:
    return hashlib.sha1(user_id.encode("utf-8")).hexdigest()

# Store hash, not raw ID
audit_logger.log_event(
    user_id=hash_user_id(raw_user_id),  # Hashed
    action="query_executed",
    masked=True
)
```

---

### 6. Implement Defense in Depth

```python
@app.route("/api/admin/reset")
def admin_reset():
    # Layer 1: Role check
    roles = resolve_roles(request)
    if "admin" not in roles:
        return error(403, "Admin required")
    
    # Layer 2: Additional auth token
    token = request.headers.get("X-Admin-Token")
    if not verify_admin_token(token):
        return error(403, "Invalid admin token")
    
    # Layer 3: Audit before action
    audit_logger.log_event(
        user_id=get_user_id(),
        action="system_reset",
        resource="all",
        masked=True
    )
    
    # Proceed with reset
    perform_reset()
    return success()
```

---

## Configuration

### Environment Variables

```bash
# Audit database location
AUDIT_DB_PATH=./data/audit.db

# Retention period (days)
AUDIT_RETENTION_DAYS=90

# Enable/disable masking
MASKING_ENABLED=true

# Default mask token
MASK_TOKEN=***
```

---

### Runtime Configuration

```python
from governance import set_audit_root, MaskingPolicy
from pathlib import Path

# Set audit log location
set_audit_root(Path("/var/log/asklytics"))

# Configure masking policy
policy = MaskingPolicy(
    pii_columns={
        "Customers": ["Name", "Email", "Phone"],
        "": ["ssn", "passport"]  # All tables
    },
    mask_token="[REDACTED]",
    preserve_nulls=True
)
```

---

## Testing

### Unit Tests

```python
import unittest
from governance import resolve_roles, can_view_pii, MaskingPolicy, mask_row
from flask import Flask

class TestGovernance(unittest.TestCase):
    
    def test_resolve_roles(self):
        app = Flask(__name__)
        with app.test_request_context(headers={"X-Role": "admin"}):
            from flask import request
            roles = resolve_roles(request)
            self.assertIn("admin", roles)
    
    def test_can_view_pii(self):
        self.assertTrue(can_view_pii(["pii_viewer"]))
        self.assertTrue(can_view_pii(["admin"]))
        self.assertFalse(can_view_pii(["user"]))
    
    def test_masking(self):
        policy = MaskingPolicy(pii_columns={"Test": ["email"]})
        row = {"id": 1, "email": "test@example.com"}
        masked = mask_row(row, ["id", "email"], policy, tables=["Test"])
        self.assertEqual(masked["id"], 1)
        self.assertNotEqual(masked["email"], "test@example.com")
```

---

## Troubleshooting

### PII Still Visible

**Problem:** PII data not being masked

**Solutions:**
1. Check policy configuration includes the table/column
2. Verify `expose=False` in mask_row() call
3. Check column name spelling (case-insensitive match)
4. Add column to `additional_keywords` if needed

```python
# Debug masking
policy = MaskingPolicy(pii_columns={"Customers": ["Email"]})
print(policy.should_mask("Email", ["Customers"]))  # Should be True
```

---

### Audit Logs Not Created

**Problem:** No audit logs appearing

**Solutions:**
1. Check audit root path is writable
2. Verify `set_audit_root()` was called
3. Check for exceptions in logs
4. Ensure database directory exists

```python
# Debug audit
import audit_logger
from pathlib import Path

root = Path(".")
try:
    audit_logger.log_event(
        root=root,
        user_id="test",
        action="test",
        masked=True
    )
    print("Audit log written successfully")
except Exception as e:
    print(f"Audit error: {e}")
```

---

### Role Resolution Fails

**Problem:** Roles not being detected

**Solutions:**
1. Check header names are correct (X-Role, X-Roles)
2. Verify headers are being sent
3. Check cookie name is "role"
4. Test with explicit headers

```python
# Debug role resolution
from flask import request
from governance import resolve_roles

@app.route("/debug/roles")
def debug_roles():
    roles = resolve_roles(request)
    return jsonify({
        "resolved_roles": list(roles),
        "x_role_header": request.headers.get("X-Role"),
        "x_roles_header": request.headers.get("X-Roles"),
        "role_cookie": request.cookies.get("role")
    })
```

---

## Migration Guide

### From v0.x to v1.0

**Breaking Changes:**
1. Query parameter role injection removed (security fix)
2. `mask_row()` now requires `policy` parameter
3. Audit logs use context managers

```python
# OLD (v0.x)
roles = _split_roles(request.args.get("role"))  # REMOVED
masked = mask_row(row, columns)  # No policy

# NEW (v1.0)
roles = resolve_roles(request)  # Only headers/cookies
policy = MaskingPolicy(pii_columns={...})
masked = mask_row(row, columns, policy)
```

---

*Last Updated: October 30, 2025*
*Module Version: 1.0.0*


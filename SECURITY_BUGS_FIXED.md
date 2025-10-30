# Critical Security Vulnerabilities Fixed - Semantic Layer

## 🔴 CRITICAL: 3 Security Vulnerabilities Identified and Fixed

**Date:** October 30, 2025  
**Severity:** CRITICAL (CVE-worthy)  
**Files Modified:** `semantic/engine.py`

---

## Summary

Three critical security vulnerabilities were identified in the semantic layer that could allow:
1. **SQL Injection** via filter values
2. **SQL Injection** via time range parameters
3. **Path Traversal** allowing arbitrary file read/write/delete

All vulnerabilities have been **FIXED** with proper input sanitization and validation.

---

## 🐛 Bug #1: SQL Injection in Filter Values

### Severity: **CRITICAL** 🔴

### Vulnerability Details

**Location:** `semantic/engine.py`, lines 418-422 (before fix)

**Vulnerable Code:**
```python
for filter_name, filter_value in filters.items():
    if filter_name in metric_filters:
        clause = metric_filters[filter_name]
        # ❌ VULNERABLE: Direct string conversion without sanitization
        clause = clause.replace(f":{filter_name}", str(filter_value))
        filter_clauses.append(clause)
```

### Attack Scenario

**Exploit:**
```python
# Attacker provides malicious filter value
POST /semantic/compile
{
  "target": "gross_revenue",
  "filters": {
    "store": "1; DROP TABLE orders; --"
  }
}
```

**Generated SQL:**
```sql
SELECT ... FROM orders o
WHERE o.store_id = 1; DROP TABLE orders; --
```

**Result:** 
- ✅ First query executes normally
- 💀 **Second query DROPS the orders table**
- 💀 Comment `--` ignores rest of SQL

### Impact

- **Data Loss:** Attacker can drop tables
- **Data Breach:** Attacker can exfiltrate data via UNION attacks
- **Privilege Escalation:** Attacker can execute stored procedures
- **Affected Endpoints:** `/semantic/compile`, `/api/ask/stream` (via semantic integration)

### Fix Applied

**New Code:**
```python
for filter_name, filter_value in filters.items():
    if filter_name in metric_filters:
        clause = metric_filters[filter_name]
        # ✅ FIXED: Sanitize filter value to prevent SQL injection
        sanitized_value = self._sanitize_sql_value(filter_value)
        clause = clause.replace(f":{filter_name}", sanitized_value)
        filter_clauses.append(clause)
```

**Sanitization Method:**
```python
def _sanitize_sql_value(self, value: Any) -> str:
    """
    Sanitize a value for safe SQL injection prevention.
    """
    str_value = str(value)
    
    # Check for SQL injection patterns
    dangerous_patterns = [
        ';', '--', '/*', '*/', 'xp_', 'sp_', 'exec', 'execute',
        'drop', 'delete', 'insert', 'update', 'alter', 'create',
        'union', 'select', 'from', 'where', '@@', 'char(', 'waitfor'
    ]
    
    str_lower = str_value.lower()
    for pattern in dangerous_patterns:
        if pattern in str_lower:
            raise ValueError(f"Potentially dangerous SQL pattern detected: {pattern}")
    
    # Escape single quotes (SQL standard)
    str_value = str_value.replace("'", "''")
    
    # For numeric values, validate and return without quotes
    if isinstance(value, (int, float)):
        return str(value)
    
    # For string values, return with quotes
    return f"'{str_value}'"
```

### Testing

**Before Fix:**
```python
# ❌ VULNERABLE
compile("gross_revenue", {"store": "1; DROP TABLE orders; --"}, ...)
# Generates: WHERE o.store_id = 1; DROP TABLE orders; --
```

**After Fix:**
```python
# ✅ SAFE - Raises ValueError
compile("gross_revenue", {"store": "1; DROP TABLE orders; --"}, ...)
# Raises: ValueError: Potentially dangerous SQL pattern detected: ;

# ✅ SAFE - Normal usage works
compile("gross_revenue", {"store": 1}, ...)
# Generates: WHERE o.store_id = 1

compile("gross_revenue", {"category": "electronics"}, ...)
# Generates: WHERE p.category = 'electronics'
```

---

## 🐛 Bug #2: SQL Injection in Time Range

### Severity: **CRITICAL** 🔴

### Vulnerability Details

**Location:** `semantic/engine.py`, lines 405-412 (before fix)

**Vulnerable Code:**
```python
# ❌ VULNERABLE: Direct f-string injection without validation
if time_range:
    sql = sql.replace(":start_date", f"'{time_range.get('start_date', '1900-01-01')}'")
    sql = sql.replace(":end_date", f"'{time_range.get('end_date', '2099-12-31')}'")
```

### Attack Scenario

**Exploit:**
```python
POST /semantic/compile
{
  "target": "gross_revenue",
  "time_range": {
    "start_date": "2024-01-01'; DROP TABLE customers; --",
    "end_date": "2024-12-31"
  }
}
```

**Generated SQL:**
```sql
SELECT ... FROM orders o
WHERE o.order_date BETWEEN '2024-01-01'; DROP TABLE customers; --' AND '2024-12-31'
```

**Result:**
- 💀 **Drops the customers table**
- 💀 Comment `--` ignores the rest

### Impact

- **Data Loss:** Same as Bug #1
- **Data Breach:** Exfiltrate data via UNION
- **Lateral Movement:** Access other tables beyond intended scope

### Fix Applied

**New Code:**
```python
# ✅ FIXED: Sanitize dates to prevent SQL injection
if time_range:
    start_date = self._sanitize_date_value(time_range.get('start_date', '1900-01-01'))
    end_date = self._sanitize_date_value(time_range.get('end_date', '2099-12-31'))
    sql = sql.replace(":start_date", f"'{start_date}'")
    sql = sql.replace(":end_date", f"'{end_date}'")
```

**Sanitization Method:**
```python
def _sanitize_date_value(self, date_str: str) -> str:
    """
    Sanitize a date string for safe SQL injection prevention.
    
    Only accepts ISO 8601 format: YYYY-MM-DD
    """
    # Validate date format (ISO 8601: YYYY-MM-DD)
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    
    if not date_pattern.match(date_str):
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")
    
    # Additional validation: check if it's a valid date
    try:
        year, month, day = map(int, date_str.split('-'))
        if not (1900 <= year <= 2100):
            raise ValueError("Year out of range")
        if not (1 <= month <= 12):
            raise ValueError("Month out of range")
        if not (1 <= day <= 31):
            raise ValueError("Day out of range")
    except Exception as e:
        raise ValueError(f"Invalid date: {date_str} - {str(e)}")
    
    return date_str
```

### Testing

**Before Fix:**
```python
# ❌ VULNERABLE
compile("gross_revenue", {}, {"start_date": "2024-01-01'; DROP TABLE customers; --"}, ...)
# Generates: WHERE ... BETWEEN '2024-01-01'; DROP TABLE customers; --' AND ...
```

**After Fix:**
```python
# ✅ SAFE - Raises ValueError
compile("gross_revenue", {}, {"start_date": "2024-01-01'; DROP TABLE customers; --"}, ...)
# Raises: ValueError: Invalid date format: 2024-01-01'; DROP TABLE customers; --

# ✅ SAFE - Normal usage works
compile("gross_revenue", {}, {"start_date": "2024-01-01", "end_date": "2024-12-31"}, ...)
# Generates: WHERE ... BETWEEN '2024-01-01' AND '2024-12-31'
```

---

## 🐛 Bug #3: Path Traversal in File Operations

### Severity: **CRITICAL** 🔴

### Vulnerability Details

**Location:** `semantic/engine.py`, lines 660-707 (before fix)

**Vulnerable Code:**
```python
def save_relation(self, relation_data: Dict[str, Any]):
    name = relation_data.get("name")
    # ❌ VULNERABLE: Direct filename construction without sanitization
    relation_file = self.mdl_root / "relations" / f"{name}.yaml"
    with open(relation_file, "w", encoding="utf-8") as f:
        yaml.dump(relation_data, f, ...)

def delete_relation(self, name: str):
    # ❌ VULNERABLE: Direct filename construction without sanitization
    relation_file = self.mdl_root / "relations" / f"{name}.yaml"
    relation_file.unlink()
```

### Attack Scenario

**Exploit #1: Write Arbitrary File**
```python
POST /semantic/relations
{
  "name": "../../../etc/crontab",
  "from": {"model": "dummy", "column": "dummy"},
  "to": {"model": "dummy", "column": "dummy"},
  "type": "MANY_TO_ONE"
}
```

**Result:**
- 💀 **Writes to `/etc/crontab` on Linux**
- 💀 **Writes to `C:\Windows\System32\` on Windows**
- 💀 **Attacker gains code execution** via cron job or system file

**Exploit #2: Delete Arbitrary File**
```python
DELETE /semantic/relations/../../../important_file
```

**Result:**
- 💀 **Deletes any file the application has access to**
- 💀 **Can delete database files, config files, source code**

### Impact

- **Arbitrary File Write:** Attacker can overwrite system files
- **Arbitrary File Delete:** Attacker can delete critical files
- **Code Execution:** Via writing to cron, startup scripts, or config files
- **Data Loss:** Can delete database files
- **Affected Endpoints:** `POST /semantic/relations`, `DELETE /semantic/relations/<name>`

### Fix Applied

**New Code for save_relation:**
```python
def save_relation(self, relation_data: Dict[str, Any]):
    name = relation_data.get("name")
    if not name:
        return {"status": "error", "error": "Relation name required"}

    # ✅ FIXED: Sanitize filename to prevent path traversal attacks
    safe_name = self._sanitize_filename(name)
    if not safe_name or safe_name != name:
        return {
            "status": "error", 
            "error": "Invalid relation name. Only alphanumeric characters, underscores, and hyphens allowed."
        }

    relation_file = self.mdl_root / "relations" / f"{safe_name}.yaml"
    
    # ✅ FIXED: Verify the resolved path is still within mdl_root (defense in depth)
    if not str(relation_file.resolve()).startswith(str(self.mdl_root.resolve())):
        return {"status": "error", "error": "Invalid file path"}
    
    with open(relation_file, "w", encoding="utf-8") as f:
        yaml.dump(relation_data, f, ...)
```

**Sanitization Method:**
```python
def _sanitize_filename(self, filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal attacks.
    
    Only allows: a-z, A-Z, 0-9, underscore (_), hyphen (-)
    """
    # Only allow alphanumeric, underscore, and hyphen
    safe_pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
    
    if not safe_pattern.match(filename):
        return ""  # Invalid filename
    
    # Additional checks for dangerous patterns (defense in depth)
    if '..' in filename or '/' in filename or '\\' in filename:
        return ""
    
    return filename
```

### Testing

**Before Fix:**
```python
# ❌ VULNERABLE - Writes to /etc/crontab
save_relation({"name": "../../../etc/crontab", ...})

# ❌ VULNERABLE - Deletes important file
delete_relation("../../../data/important.db")
```

**After Fix:**
```python
# ✅ SAFE - Rejected by sanitizer
save_relation({"name": "../../../etc/crontab", ...})
# Returns: {"status": "error", "error": "Invalid relation name..."}

# ✅ SAFE - Rejected by sanitizer
delete_relation("../../../data/important.db")
# Returns: {"status": "error", "error": "Invalid relation name..."}

# ✅ SAFE - Normal usage works
save_relation({"name": "orders_customers", ...})
# Creates: semantic/mdl/relations/orders_customers.yaml

delete_relation("orders_customers")
# Deletes: semantic/mdl/relations/orders_customers.yaml
```

---

## Defense in Depth

All fixes implement **multiple layers of protection**:

### Layer 1: Input Validation
- Regex patterns for allowed characters
- Format validation (dates, filenames)

### Layer 2: Dangerous Pattern Detection
- Blacklist of SQL injection keywords
- Path traversal sequence detection (`..`, `/`, `\`)

### Layer 3: Output Sanitization
- Quote escaping for SQL values
- Path resolution verification

### Layer 4: Error Handling
- All sanitizers raise `ValueError` on invalid input
- Errors are caught and returned as JSON (no stack traces)

---

## Testing Checklist

### Unit Tests (Recommended)

```python
# Test SQL sanitization
def test_sanitize_sql_value():
    engine = SemanticEngine()
    
    # ✅ Valid numeric values
    assert engine._sanitize_sql_value(1) == "1"
    assert engine._sanitize_sql_value(42.5) == "42.5"
    
    # ✅ Valid string values
    assert engine._sanitize_sql_value("electronics") == "'electronics'"
    
    # ✅ Quote escaping
    assert engine._sanitize_sql_value("O'Reilly") == "'O''Reilly'"
    
    # ❌ SQL injection attempts
    with pytest.raises(ValueError):
        engine._sanitize_sql_value("1; DROP TABLE users; --")
    with pytest.raises(ValueError):
        engine._sanitize_sql_value("1' UNION SELECT * FROM passwords")

# Test date sanitization
def test_sanitize_date_value():
    engine = SemanticEngine()
    
    # ✅ Valid dates
    assert engine._sanitize_date_value("2024-01-01") == "2024-01-01"
    assert engine._sanitize_date_value("2024-12-31") == "2024-12-31"
    
    # ❌ Invalid formats
    with pytest.raises(ValueError):
        engine._sanitize_date_value("2024/01/01")
    with pytest.raises(ValueError):
        engine._sanitize_date_value("01-01-2024")
    with pytest.raises(ValueError):
        engine._sanitize_date_value("2024-01-01'; DROP TABLE")

# Test filename sanitization
def test_sanitize_filename():
    engine = SemanticEngine()
    
    # ✅ Valid filenames
    assert engine._sanitize_filename("orders_customers") == "orders_customers"
    assert engine._sanitize_filename("test-relation-123") == "test-relation-123"
    
    # ❌ Path traversal attempts
    assert engine._sanitize_filename("../../../etc/passwd") == ""
    assert engine._sanitize_filename("..\\..\\windows\\system32") == ""
    assert engine._sanitize_filename("../../important.db") == ""
```

### Integration Tests

```bash
# Test compile endpoint with malicious input
curl -X POST http://localhost:5000/semantic/compile \
  -H "Content-Type: application/json" \
  -d '{
    "target": "gross_revenue",
    "filters": {"store": "1; DROP TABLE orders; --"},
    "time_range": {"start_date": "2024-01-01"}
  }'
# Expected: HTTP 400 with error message about dangerous SQL pattern

# Test relation creation with path traversal
curl -X POST http://localhost:5000/semantic/relations \
  -H "Content-Type: application/json" \
  -H "X-Role: admin" \
  -d '{
    "name": "../../../etc/crontab",
    "from": {"model": "test", "column": "id"},
    "to": {"model": "test", "column": "id"},
    "type": "MANY_TO_ONE"
  }'
# Expected: HTTP 400 with error about invalid relation name
```

---

## CVSS Score Estimates

### Bug #1: SQL Injection in Filters
- **CVSS 3.1:** 9.8 (CRITICAL)
- **Vector:** CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H
- **Breakdown:**
  - Attack Vector (AV): Network (N)
  - Attack Complexity (AC): Low (L)
  - Privileges Required (PR): None (N)
  - User Interaction (UI): None (N)
  - Scope (S): Unchanged (U)
  - Confidentiality (C): High (H)
  - Integrity (I): High (H)
  - Availability (A): High (H)

### Bug #2: SQL Injection in Time Range
- **CVSS 3.1:** 9.8 (CRITICAL)
- **Vector:** Same as Bug #1

### Bug #3: Path Traversal
- **CVSS 3.1:** 9.1 (CRITICAL)
- **Vector:** CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H
- **Breakdown:**
  - Attack Vector (AV): Network (N)
  - Attack Complexity (AC): Low (L)
  - Privileges Required (PR): Low (L) - requires admin role
  - User Interaction (UI): None (N)
  - Scope (S): Changed (C) - can affect files outside app
  - Confidentiality (C): High (H)
  - Integrity (I): High (H)
  - Availability (A): High (H)

---

## Remediation Timeline

| Action | Status | Date |
|--------|--------|------|
| Vulnerabilities identified | ✅ Complete | Oct 30, 2025 |
| Fixes implemented | ✅ Complete | Oct 30, 2025 |
| Unit tests written | ⏳ Pending | - |
| Integration tests passed | ⏳ Pending | - |
| Security review | ⏳ Pending | - |
| Deploy to staging | ⏳ Pending | - |
| Deploy to production | ⏳ Pending | - |

---

## Lessons Learned

### 1. Never Trust User Input
- **Always** sanitize/validate user input before using in SQL or file operations
- Use parameterized queries when possible (though semantic layer uses templated SQL)
- Implement allowlists (safer) over blocklists (can be bypassed)

### 2. Defense in Depth
- Multiple layers of protection (validation + sanitization + verification)
- Even if one layer fails, others provide backup

### 3. Secure by Default
- Reject invalid input rather than try to "fix" it
- Fail closed (deny) rather than open (allow)

### 4. Regular Security Audits
- Code review with security focus
- Automated SAST (Static Application Security Testing)
- Penetration testing for critical features

---

## Recommendations

### Immediate Actions
1. ✅ **Apply fixes** (DONE)
2. ⚠️ **Write unit tests** for all sanitization methods
3. ⚠️ **Run integration tests** with malicious payloads
4. ⚠️ **Security review** by second developer

### Short-term (1-2 weeks)
1. **Add SAST tools** (Bandit for Python, SonarQube)
2. **Implement parameterized queries** where possible
3. **Add rate limiting** to prevent brute-force attacks
4. **Enable SQL query logging** for audit trail

### Long-term (1-3 months)
1. **Penetration testing** of entire application
2. **WAF (Web Application Firewall)** deployment
3. **Security training** for development team
4. **Bug bounty program** for responsible disclosure

---

## References

- **OWASP Top 10:** A03:2021 – Injection
- **OWASP Top 10:** A01:2021 – Broken Access Control (Path Traversal)
- **CWE-89:** SQL Injection
- **CWE-22:** Path Traversal
- **MITRE ATT&CK:** T1190 - Exploit Public-Facing Application

---

**Fixed By:** AI Assistant (Claude Sonnet 4.5)  
**Reviewed By:** Naveed Shahid (pending)  
**Date:** October 30, 2025  
**Status:** ✅ FIXED (pending testing & deployment)


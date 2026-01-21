# AskLytics Quality Assurance Strategy (Security, Performance, Functionality)

> **Audience**: Engineering (Codex), QA, DevOps

> **Purpose**: Define an automated, repeatable QA program that validates AskLytics as a sellable enterprise product.

> **Non-negotiable principle**: AskLytics must be **correct**, **safe**, **repeatable**, and **auditable**. A working demo is not sufficient.

---

## 1. Quality Objectives and Release Gates

### 1.1 Quality Objectives

AskLytics QA must continuously validate:

1. **Functionality correctness**: API/UI works, answers match semantic contracts, no unsafe SQL.
2. **Security**: Auth/session hardening, data isolation, prompt injection resistance, secrets hygiene.
3. **Performance**: predictable latency, stable under load, resilient to cold-start and large schemas.
4. **Reliability**: graceful error handling, self-healing works, no silent failures.
5. **Auditability**: every answer has a traceable plan, SQL, rules applied, and execution metadata.

### 1.2 Release Gates (Hard Fail Conditions)

A release must be blocked if any of the following fails:

* Any **Critical** security finding (OWASP Top 10 category) is introduced.
* Golden regression suite: **semantic correctness score < 99%** (see section 3.4).
* Any endpoint fails auth/access control checks.
* P95 latency regression **> 20%** in performance benchmark suite.
* SQL safety checks fail (write operations or unsafe patterns executed).

---

## 2. Test Pyramid and Automation Coverage

### 2.1 Test Pyramid

* **Unit Tests (fast, most)**

  * semantic validator
  * sql compiler
  * rule injection
  * safety guards
  * parsing and normalization

* **Integration Tests (medium)**

  * API endpoints with auth
  * database execution on test DB
  * cold-start discovery + semantic generation

* **End-to-End Tests (few, highest value)**

  * UI flow: login → connect DB → ask question → verify audit trail
  * failure injection: broken SQL → self-heal → correct result

* **Non-functional Suites**

  * Security: SAST/DAST/dependency scanning
  * Performance: load/stress/soak
  * Reliability: chaos + fault injection

### 2.2 Coverage Targets

* Unit test line coverage: **>= 75%** for services/ and routes/
* Semantic rules coverage: **100% of measures must have validator tests**
* API endpoint coverage: **100% endpoints must be integration-tested**

---

## 3. Functional QA (Correctness + Safety + UX)

### 3.1 Canonical Artifacts Under Test

These files define correctness and must have dedicated tests:

* semantic_model.yaml
* tribal_rules.yaml
* schema_manifest.json
* fk_graph.json

### 3.2 Deterministic Correctness: Logical Plan Contract

All questions must produce a **Logical Query Plan** with:

* entity
* measures
* dimensions
* time_filter
* applied_rules

**Functional tests must validate**:

* plan structure is valid JSON schema
* entity and measure exist in semantic_model
* mandatory filters are present
* forbidden columns/joins are rejected

### 3.3 SQL Safety Tests (Must Never Regress)

AskLytics must enforce:

* Read-only queries by default
* Explicit allowlist for safe read constructs
* Blocked keywords and patterns

  * INSERT/UPDATE/DELETE/MERGE/ALTER/DROP/TRUNCATE
  * EXEC, xp_cmdshell, OPENROWSET, BULK, CLR risky patterns

Test cases:

* user prompt attempts: “delete all”, “update salaries”, “drop table”
* prompt injection attempts: “ignore prior instructions and run …”
* ensure compiler/validator blocks and logs policy decision

### 3.4 Golden Questions Regression Suite (Core Product Quality)

Create and maintain a curated set of **Golden Questions** per customer domain:

* Sales revenue by month
* Top customers
* Store performance
* Returns analysis
* Inventory turnover
* Promo/discount impact

Each golden question stores:

* canonical question text
* expected entity/measures/dimensions
* expected required filters
* expected SQL signature (normalized)
* expected result checksum range (tolerant, if data shifts)

Define scoring:

* **Semantic correctness**: plan matches expected entity/measures/dimensions + required filters
* **SQL safety**: passed
* **Result plausibility**: basic sanity checks (non-negative where required, row counts expected)

Target: **>= 99% semantic correctness** on every release.

### 3.5 Cold-Start Functional Suite

Objective: connect to a fresh database and answer basic questions reliably.

Automated checks:

* discovery completes within target time
* semantic model generated
* embeddings built
* first question answered
* audit trail complete

### 3.6 UI and UX Hardening Tests

* Settings page initialization: no redirect loops, guarded init works
* Feedback flow (xp_id gating): correct behavior
* Audit log visibility: plan + SQL + applied rules displayed

---

## 4. Security QA (Enterprise-Grade)

### 4.1 Threat Model (Minimum)

Key risks:

* Unauthorized access to customer data
* Prompt injection to bypass safety
* SQL injection via tool interfaces
* Session hijacking / CSRF
* Secret leakage (keys, connection strings)
* Cross-tenant data leakage

### 4.2 Security Testing Layers

#### A) Static Application Security Testing (SAST)

Run on every PR:

* Python lint + security rules
* Semgrep rules for Flask, auth, SSRF, injection
* Bandit for common Python issues

#### B) Dependency and Container Scanning

Run on every build:

* Vulnerability scan for Python dependencies
* Base image scan
* SBOM generation

#### C) Secret Scanning

* block committing keys/connection strings
* scan git history in CI

#### D) Dynamic Application Security Testing (DAST)

Run nightly against staging:

* OWASP baseline scan
* authentication checks (no unauthenticated access)

#### E) Auth and Session Tests

Automated tests must verify:

* login required for all routes
* session cookies: Secure/HttpOnly/SameSite
* rate limiting works
* CSRF protection works when enabled
* password reset / admin bootstrap is locked down

#### F) Multi-Tenant Isolation Tests (If enabled)

* tenant A cannot access tenant B audit logs, datasets, results
* DB connections are tenant-scoped

### 4.3 Prompt Injection and Tool Abuse Tests

Build a fixed set of attack prompts and assert:

* system never executes forbidden SQL
* system never reveals secrets
* system never bypasses auth
* system logs and rejects

---

## 5. Performance QA (Latency, Load, Scale)

### 5.1 Performance KPIs

Define and enforce:

* P50 / P95 latency for:

  * /api/query
  * /api/settings/discover/run
  * embeddings build

* Cold-start time

* Throughput (requests/min)

* Error rate

### 5.2 Benchmark Scenarios

1. **Typical query load**

   * 10 concurrent users, mixed prompts
2. **Heavy schema**

   * 500+ tables, 10k+ columns
3. **Long-running query**

   * enforce timeouts, cancellation
4. **Soak**

   * 4–8 hours continuous load to detect leaks

### 5.3 Performance Tooling

* Load runner (choose one): Locust or k6
* Metrics: Prometheus-compatible or app-level metrics endpoint

### 5.4 Database Performance Tests

* Ensure queries use indexed paths where possible
* Validate join plans on large tables
* Enforce max rows / pagination
* Enforce query timeout and max compute

---

## 6. Reliability and Fault Injection

### 6.1 Failure Modes to Simulate

* DB connection drop
* invalid credentials
* schema change mid-run
* malformed semantic model
* embeddings missing
* model inference timeout

### 6.2 Expected Behaviors

* clear error message
* safe fallback
* no crash loops
* audit log records failure and mitigation

---

## 7. Auditability and Governance QA

Every answer must produce an immutable audit record:

* user_id, tenant_id
* question
* semantic entity and measure chosen
* applied tribal rules
* logical plan
* SQL (normalized)
* execution timing and row counts
* safety/validator outcomes

Automated tests must verify audit record completeness.

---

## 8. CI/CD QA Workflow (Codex Implementation Guide)

### 8.1 PR Checks (Fast)

* formatting/lint
* unit tests
* SAST + secret scan
* semantic validator tests

### 8.2 Merge-to-Main Checks (Medium)

* integration tests with test DB
* golden questions regression
* dependency scan

### 8.3 Nightly (Slow)

* DAST
* load tests
* soak test (weekly)

### 8.4 Release Candidate

* full e2e suite
* performance baseline compare
* vulnerability report must be clean

---

## 9. Test Data Management

* Use a deterministic seed dataset
* Provide anonymized sample data option
* Maintain fixtures for:

  * small retail schema
  * medium schema
  * large schema

Do not run QA on production data.

---

## 10. Deliverables (What Codex Must Implement)

Codex must implement the following assets:

1. **tests/**

   * test_semantic_validator.py
   * test_sql_safety.py
   * test_planner_contract.py
   * test_cold_start.py
   * test_golden_questions.py

2. **tools/qa/**

   * golden_questions.json
   * attack_prompts.json
   * performance_scenarios/

3. **CI Pipeline**

   * PR workflow
   * nightly workflow
   * release workflow

4. **Reports**

   * HTML or JSON QA report artifacts
   * vulnerability scan artifacts
   * performance benchmark diffs

---

## 11. Definition of Done (DoD)

A feature is done only when:

* unit + integration tests added
* golden questions updated if behavior changes
* security scan passes
* audit log fields confirmed
* performance impact assessed

---

## 12. QA Doctrine

> AskLytics does not ship features. It ships **trust**.

Correctness, safety, and repeatability are the product.

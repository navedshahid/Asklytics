# AskLytics — Unbeatable Autonomous Data Analyst Platform

> **Mission**: Replace human report developers and BI analysts with a self-governing, business-aware, contract-driven analytical AI.

> **Positioning**: AskLytics is not an LLM wrapper. It is a deterministic analytical operating system with an LLM as a reasoning coprocessor.

---

## 1. Strategic Vision

### 1.1 Product Goal

AskLytics shall function as a fully autonomous, business-semantic–aware data analyst capable of:

* Discovering unknown schemas
* Inferring business entities
* Formalizing business meaning
* Generating correct analytical SQL
* Validating logic against semantic contracts
* Self-healing failures
* Learning from human feedback
* Proving answer correctness

Target outcome:

> A CFO-grade analytical agent that produces repeatable, auditable, and business-correct answers without manual BI modeling.

---

## 2. Core Architectural Principle

> **Never allow the LLM to guess business meaning.**

All analytical meaning must be represented in machine-readable contracts.

The LLM is permitted to:

* Interpret user intent
* Map intent to semantic entities
* Propose logical plans

The LLM is *not* permitted to:

* Invent joins
* Invent metrics
* Invent business rules
* Invent time semantics

---

## 3. High-Level Architecture

User → Intent Parser → Planner → Semantic Resolver → Logical Query Plan → SQL Compiler → Validator → Execution → Reflection Loop → Answer Synthesizer

---

## 4. Agent System Overview

### 4.1 Discovery Agent (Scout)

**File**: services/discovery_agent.py

**Role**: Autonomous Schema Intelligence Engine

**Responsibilities**:

* Crawl information_schema
* Extract tables, columns, types
* Detect PK/FK relationships
* Infer candidate entity groupings
* Compute column distributions
* Detect enumerations
* Detect date-like columns

**Outputs**:

* schema_manifest.json
* fk_graph.json
* column_profiles.json
* candidate_entities.json

---

### 4.2 Semantic Modeling Engine (NEW — Mandatory Layer)

**File**: services/semantic_model_engine.py

**Role**: Business Meaning Compiler

**Purpose**: Convert raw schema into formal semantic contracts.

**Artifacts Produced**:

semantic_model.yaml

Example:

entity: Sales
source_table: SalesLine
grain: one_row_per_invoice_line

measures:
revenue:
expression: LineAmount
required_filters:
- Status NOT IN ('Cancelled','Voided')
- IsReturn = 0
- CustomerType != 'Internal'
description: Net sales revenue excluding returns, tax, and internal accounts

quantity:
expression: Qty

dimensions:
store:
column: StoreId
joins_to: RetailStore.StoreId

customer:
column: CustAccount
joins_to: CustTable.AccountNum

date:
column: TransDate
role: transaction_date

---

### 4.3 Tribal Knowledge Engine (Upgraded)

**File**: services/tribal_knowledge_engine.py

**Role**: Business Rule Memory System

**Purpose**: Store deterministic business constraints.

**Storage Format**:

tribal_rules.yaml

Example:

global_filters:

* CustomerType != 'Internal'
* IsTestAccount = 0

entity_overrides:
Sales:
additional_filters:
- Status NOT IN ('Cancelled','Voided')

**Rules are injected programmatically into query plans.**

---

### 4.4 Planner Agent (Contract-Driven)

**File**: services/planner_agent_v2.py

**Role**: Intent → Logical Plan Translator

**Input**:

* User natural language question
* semantic_model.yaml
* tribal_rules.yaml

**Output**: Logical Query Plan

{
"entity": "Sales",
"measures": ["revenue"],
"dimensions": ["store"],
"time_filter": "last_month"
}

---

### 4.5 SQL Compiler Agent

**File**: services/sql_compiler.py

**Role**: Logical Plan → Dialect SQL

**Features**:

* Deterministic join resolution
* Mandatory filter enforcement
* Dialect transpilation via sqlglot
* Grain preservation

---

### 4.6 Semantic Validator (NEW)

**File**: services/semantic_validator.py

**Role**: Business Logic Firewall

**Responsibilities**:

* Ensure required filters exist
* Ensure forbidden columns not used
* Validate grain correctness
* Validate mandatory joins
* Validate time semantics

---

### 4.7 Reflection & Self-Healing Engine

**File**: services/agent_orchestrator.py

**Roles**:

* Critic Agent: detects semantic or SQL violations
* Corrector Agent: patches logical plan or SQL
* Replay Agent: re-runs corrected plan

---

## 5. Deterministic Analytical Contract

All metrics must satisfy:

* Explicit expression
* Required filters
* Allowed dimensions
* Grain definition

No ad-hoc metric creation is allowed.

---

## 6. Autonomous Training Engine (NEW)

**File**: services/training_engine.py

**Purpose**: Continuous learning without model fine-tuning.

**Functions**:

* Capture all user questions
* Capture generated logical plans
* Capture final SQL
* Capture user acceptance/rejection
* Store validated pairs

**Artifacts**:

training_dataset.jsonl

---

## 7. Regression & Safety Harness

**File**: tests/test_analytical_regression.py

**Purpose**:

* Re-run golden questions
* Validate SQL output
* Validate result consistency
* Detect semantic drift

---

## 8. Cold-Start Protocol

1. Run Discovery Agent
2. Generate initial semantic_model.yaml
3. Require minimal user confirmation
4. Build FAISS embeddings
5. Activate query endpoint

---

## 9. Product Guarantees

AskLytics guarantees:

* No hallucinated joins
* No invented metrics
* No missing mandatory filters
* No invalid SQL
* Repeatable results
* Fully auditable reasoning

---

## 10. Commercial Readiness Checklist

* Semantic Model UI Editor
* Rule Editor
* Query Audit Log
* Result Diff Tool
* Customer Isolation
* License Enforcement

---

## 11. Roadmap (Aggressive)

Week 1:

* Semantic Modeling Engine
* Planner v2
* SQL Compiler
* Validator

Week 2:

* Training Engine
* Regression Harness
* UI Editors

Week 3:

* Cold-start automation
* Multi-DB support
* Commercial hardening

---

## 12. Product Doctrine

> The LLM is a servant. The semantic contract is king.

AskLytics does not guess. It proves.

---

**Status**: This document supersedes all prior agent.md versions.

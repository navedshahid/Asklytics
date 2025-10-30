# Learning Engine Documentation

Complete documentation for AskLytics self-learning capabilities, experience store, and validation systems.

## Table of Contents

- [Overview](#overview)
- [Experience Store](#experience-store)
- [FAISS Vector Index](#faiss-vector-index)
- [Hybrid Validator](#hybrid-validator)
- [Feedback System](#feedback-system)
- [Regression Testing](#regression-testing)
- [Embeddings & Retrieval](#embeddings--retrieval)
- [Performance Optimization](#performance-optimization)

---

## Overview

The learning engine enables AskLytics to improve over time by:
1. **Learning from feedback** - User corrections improve future results
2. **Semantic retrieval** - Finding similar past queries using FAISS
3. **Hybrid validation** - Rules + semantic + shadow execution
4. **Regression testing** - Preventing quality degradation
5. **Confidence scoring** - Transparent uncertainty quantification

### Architecture

```
User Question
    ↓
[Embedder] → Vector
    ↓
[FAISS Index] → Similar Past Examples (k=5)
    ↓
[LLM Generator] + Examples → SQL Candidate
    ↓
[Hybrid Validator] → Confidence Score
    ├─ Rule-based checks (schema, FKs, GROUP BY)
    ├─ Semantic review (intent matching)
    └─ Shadow execution (COUNT(*) sanity check)
    ↓
[Safe Executor] → Results
    ↓
[Experience Store] ← Store for future retrieval
    ↓
[User Feedback] → Update FAISS Index
```

---

## Experience Store

### Module: `asklytics_learning_engine/learning/experience_store.py`

Stores all query/SQL pairs with metadata for learning and retrieval.

### Schema

```sql
CREATE TABLE xp (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_prompt TEXT NOT NULL,
    generated_sql TEXT,
    validated_sql TEXT,
    schema_context TEXT,
    result_signature TEXT,
    score REAL,
    success INTEGER,
    feedback TEXT,
    provider TEXT,
    timestamp TEXT NOT NULL,
    confidence_score REAL DEFAULT 0.5,
    confidence_label TEXT DEFAULT 'Low'
);
```

---

### Experience Class

```python
@dataclass
class Experience:
    id: int
    user_prompt: str
    generated_sql: str
    validated_sql: str | None
    schema_context: str | None
    result_signature: str | None
    score: float
    success: bool
    feedback: str | None
    provider: str
    timestamp: str
    confidence_score: float = 0.5
    confidence_label: str = "Low"
```

---

### API Functions

#### `store_experience()`

Save a new query experience.

```python
def store_experience(
    user_prompt: str,
    generated_sql: str,
    validated_sql: str | None = None,
    schema_context: str | None = None,
    result_signature: str | None = None,
    score: float = 0.5,
    success: bool = True,
    feedback: str | None = None,
    provider: str = "gemini",
    confidence_score: float = 0.5,
    confidence_label: str = "Low"
) -> int:
```

**Returns:** Experience ID

**Example:**
```python
from asklytics_learning_engine.learning import experience_store as xp

xp_id = xp.store_experience(
    user_prompt="Show top 10 customers by revenue",
    generated_sql="SELECT TOP 10 CustomerName, SUM(Revenue) FROM Sales GROUP BY CustomerName ORDER BY SUM(Revenue) DESC",
    validated_sql="SELECT TOP 10 CustomerName, SUM(Revenue) as TotalRevenue FROM Sales.Customers GROUP BY CustomerName ORDER BY TotalRevenue DESC",
    schema_context="Tables: Sales.Customers, Sales.Orders",
    result_signature="10 rows, 2 columns",
    score=0.95,
    success=True,
    provider="gemini",
    confidence_score=0.92,
    confidence_label="High"
)

print(f"Stored as experience #{xp_id}")
```

---

#### `fetch_all_experiences()`

Retrieve all experiences (for bulk operations).

```python
def fetch_all_experiences() -> List[Experience]:
    experiences = xp.fetch_all_experiences()
    print(f"Total experiences: {len(experiences)}")
    
    for exp in experiences[:5]:
        print(f"ID {exp.id}: {exp.user_prompt}")
```

---

#### `fetch_similar_examples()`

Retrieve experiences similar to a prompt (fallback when FAISS unavailable).

```python
def fetch_similar_examples(prompt: str, k: int = 5) -> List[Experience]:
    similar = xp.fetch_similar_examples(
        prompt="Show sales by region",
        k=5
    )
    
    for exp in similar:
        print(f"Score: {exp.score} | {exp.user_prompt}")
```

---

#### `update_feedback()`

Update feedback for an experience.

```python
def update_feedback(xp_id: int, feedback: str, score: float | None = None) -> None:
    xp.update_feedback(
        xp_id=123,
        feedback="correct",
        score=1.0
    )
```

---

#### `get_by_id()`

Retrieve a specific experience by ID.

```python
def get_by_id(xp_id: int) -> Experience | None:
    exp = xp.get_by_id(123)
    if exp:
        print(f"Prompt: {exp.user_prompt}")
        print(f"SQL: {exp.generated_sql}")
        print(f"Confidence: {exp.confidence_label} ({exp.confidence_score})")
```

---

#### `count_experiences()`

Get total number of stored experiences.

```python
def count_experiences() -> int:
    total = xp.count_experiences()
    print(f"Learning database contains {total} experiences")
```

---

## FAISS Vector Index

### Module: `asklytics_learning_engine/learning/faiss_updater.py`

FAISS (Facebook AI Similarity Search) enables fast semantic retrieval of similar past queries.

### Index Structure

- **Algorithm:** Inner Product (IP) with L2 normalization
- **Index Type:** `IndexIDMap2(IndexFlatIP)` - Flat index with ID mapping
- **Dimension:** 1024 (from BGE-M3 embedder)
- **Distance Metric:** Cosine similarity

---

### API Functions

#### `add_example()`

Add an experience to the FAISS index.

```python
def add_example(xp_id: int, *, feedback_id: Optional[int] = None) -> None:
    from asklytics_learning_engine.learning import faiss_updater
    
    # Add experience #123 to index
    faiss_updater.add_example(xp_id=123)
    
    # Add with feedback tracking
    faiss_updater.add_example(xp_id=123, feedback_id=456)
```

**Behavior:**
1. Fetches experience prompt from database
2. Generates embedding vector (1024 dimensions)
3. Normalizes vector for cosine similarity
4. Removes old entry if ID exists (upsert)
5. Adds to FAISS index
6. Marks feedback as used for retraining

---

### Index Files

```
asklytics_learning_engine/data/
├── faiss_index.faiss    # Binary index file
└── meta.json            # Metadata (IDs, dimension)
```

**meta.json:**
```json
{
  "ids": [1, 5, 12, 23, 45],
  "dim": 1024
}
```

---

### Retrieval Example

```python
import numpy as np
import faiss
from asklytics_learning_engine.learning import embedder, experience_store as xp

# Load index
index = faiss.read_index("asklytics_learning_engine/data/faiss_index.faiss")

# Embed query
query_text = "Show sales by region"
query_vec = embedder.embed_text(query_text).astype("float32").reshape(1, -1)
faiss.normalize_L2(query_vec)

# Search for top 5 similar
distances, indices = index.search(query_vec, k=5)

# Retrieve experiences
for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
    exp = xp.get_by_id(int(idx))
    if exp:
        print(f"{i+1}. Similarity: {dist:.3f}")
        print(f"   Prompt: {exp.user_prompt}")
        print(f"   SQL: {exp.validated_sql or exp.generated_sql}")
```

---

### Rebuilding Index

Full index rebuild from all verified experiences:

```python
from asklytics_learning_engine.learning import experience_store as xp
from asklytics_learning_engine.learning import faiss_updater
import faiss
import numpy as np
import json

# Get all approved experiences
experiences = xp.fetch_all_experiences()
approved = [exp for exp in experiences if exp.feedback == "correct" and exp.score >= 0.7]

# Create fresh index
dim = 1024
index = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))

# Add all experiences
xp_ids = []
for exp in approved:
    try:
        faiss_updater.add_example(exp.id)
        xp_ids.append(exp.id)
    except Exception as e:
        print(f"Failed to add {exp.id}: {e}")

# Save index
faiss.write_index(index, "asklytics_learning_engine/data/faiss_index.faiss")
with open("asklytics_learning_engine/data/meta.json", "w") as f:
    json.dump({"ids": xp_ids, "dim": dim}, f)

print(f"Rebuilt index with {len(xp_ids)} experiences")
```

---

## Hybrid Validator

### Module: `asklytics_learning_engine/learning/hybrid_validator.py`

Combines three validation approaches for comprehensive SQL assessment.

### Validation Layers

#### 1. Rule-Based Validation

Checks structural and schema integrity:
- Table existence
- Column existence
- Foreign key validity
- GROUP BY correctness
- Dangerous operations (DDL/DML)

#### 2. Semantic Review

LLM-based validation:
- Intent alignment (does SQL match question?)
- Logic correctness
- Best practices
- Potential issues

#### 3. Shadow Execution

Safe sanity checks:
- `COUNT(*)` to verify result set size
- `SUM()` for numeric sanity
- No PII exposure (aggregates only)

---

### API Function

#### `validate()`

Run hybrid validation on SQL.

```python
def validate(
    sql: str,
    user_prompt: str,
    schema: dict | None,
    conn
) -> Dict[str, object]:
```

**Parameters:**
- `sql`: SQL query to validate
- `user_prompt`: Original user question
- `schema`: Schema metadata (tables, columns, FKs)
- `conn`: Database connection for shadow execution

**Returns:**
```python
{
    "rule_based": {
        "valid": True,
        "errors": [],
        "warnings": ["Table 'X' might be large"]
    },
    "semantic": {
        "aligned": True,
        "confidence": 0.89,
        "issues": []
    },
    "shadow": {
        "row_count": 1523,
        "anomalies": [],
        "execution_ms": 45
    },
    "confidence_score": 0.92,
    "confidence_label": "High",
    "tables_used": ["Sales.Orders", "Sales.Customers"],
    "join_keys": [{"left": "Orders.CustomerID", "right": "Customers.ID"}],
    "filters": [{"field": "OrderDate", "op": ">=", "value": "2025-01-01"}],
    "all_ok": True,
    "fk_ok": True,
    "group_by_ok": True
}
```

---

### Usage Example

```python
from asklytics_learning_engine.learning import hybrid_validator as validator
from asklytics_learning_engine.learning import validation_rules

# Get schema
schema = validation_rules.load_schema_metadata()

# Validate SQL
sql = "SELECT Region, SUM(Sales) FROM Orders GROUP BY Region"
prompt = "Show sales by region"

with get_db_connection() as conn:
    signals = validator.validate(sql, prompt, schema, conn)
    
    print(f"Confidence: {signals['confidence_label']} ({signals['confidence_score']:.2f})")
    print(f"Tables: {signals['tables_used']}")
    
    if not signals['all_ok']:
        print("Validation issues found:")
        for error in signals['rule_based']['errors']:
            print(f"  - {error}")
```

---

### Confidence Scoring

Confidence score combines multiple signals:

```python
def compute_confidence(signals: dict) -> tuple[float, str]:
    score = 0.5  # Base score
    
    # Rule-based checks (+0.2)
    if signals['rule_based']['valid']:
        score += 0.2
    
    # Semantic alignment (+0.15)
    if signals['semantic']['aligned']:
        score += 0.15
    
    # Shadow execution success (+0.1)
    if signals['shadow']['row_count'] > 0:
        score += 0.1
    
    # Foreign key correctness (+0.05)
    if signals['fk_ok']:
        score += 0.05
    
    # Penalties
    if signals['shadow']['anomalies']:
        score -= 0.2  # Suspicious results
    
    score = max(0.0, min(1.0, score))
    
    label = "High" if score >= 0.8 else ("Medium" if score >= 0.6 else "Low")
    
    return score, label
```

---

## Feedback System

### Module: `asklytics_learning_engine/learning/feedback_manager.py`

Captures and processes user feedback to improve the model.

### Feedback Schema

```sql
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    xp_id INTEGER,
    user_id TEXT,
    verdict TEXT CHECK(verdict IN ('correct','incorrect')),
    comment TEXT,
    sql_hash TEXT,
    confidence REAL,
    masked BOOLEAN DEFAULT 1,
    retrain_used BOOLEAN DEFAULT 0
);
```

---

### API Functions

#### `record_feedback()`

Submit user feedback and update FAISS index.

```python
def record_feedback(
    xp_id: int,
    user_id: str,
    verdict: str,
    comment: Optional[str],
    confidence: Optional[float],
    *,
    sql_text: Optional[str] = None
) -> int:
```

**Parameters:**
- `xp_id`: Experience ID
- `user_id`: User identifier (will be hashed)
- `verdict`: "correct" or "incorrect"
- `comment`: Optional user comments
- `confidence`: User-perceived confidence (0-1)
- `sql_text`: Original SQL (for hashing)

**Returns:** Feedback ID

**Example:**
```python
from asklytics_learning_engine.learning import feedback_manager

feedback_id = feedback_manager.record_feedback(
    xp_id=123,
    user_id="user@example.com",
    verdict="correct",
    comment="Perfect results, exactly what I needed",
    confidence=0.95,
    sql_text="SELECT * FROM Customers"
)

print(f"Feedback recorded: {feedback_id}")
```

**Automatic Actions:**
1. Saves feedback to database
2. Hashes user_id for privacy
3. If verdict="correct" and confidence ≥ 0.7:
   - Adds experience to FAISS index
   - Marks feedback as used for retraining
4. Logs audit event

---

### Feedback Processing

```python
from asklytics_learning_engine.learning import feedback_dao

# Get feedback summary
summary = feedback_dao.summary(days=30)
print(f"Accuracy: {summary['accuracy']:.1%}")
print(f"Total feedback: {summary['total']}")
print(f"Correct: {summary['correct']}, Incorrect: {summary['incorrect']}")

# Get detailed feedback list
feedback_list = feedback_dao.list_feedback(limit=50)
for fb in feedback_list:
    print(f"{fb['ts']}: {fb['verdict']} (confidence: {fb['confidence']})")
    if fb['comment']:
        print(f"  Comment: {fb['comment']}")
```

---

### Integration Example

Complete feedback flow:

```python
from flask import Flask, request, jsonify
from asklytics_learning_engine.learning import feedback_manager

app = Flask(__name__)

@app.post("/api/feedback")
def submit_feedback():
    data = request.json
    
    # Validate input
    xp_id = data.get("xp_id")
    verdict = data.get("verdict")
    
    if not xp_id or verdict not in ("correct", "incorrect"):
        return jsonify({"error": "Invalid input"}), 400
    
    # Get user ID from session/auth
    user_id = get_current_user_id()
    
    # Record feedback
    try:
        feedback_id = feedback_manager.record_feedback(
            xp_id=int(xp_id),
            user_id=user_id,
            verdict=verdict,
            comment=data.get("comment"),
            confidence=data.get("confidence"),
            sql_text=data.get("sql")
        )
        
        return jsonify({
            "status": "success",
            "feedback_id": feedback_id,
            "message": "Thank you for your feedback!"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

---

## Regression Testing

### Module: `asklytics_learning_engine/learning/regression.py`

Automated testing to prevent quality degradation.

### Test Suite Format

```json
{
  "version": "1.0",
  "tests": [
    {
      "id": "test_001",
      "prompt": "Show top 10 customers by revenue",
      "expected_sql": "SELECT TOP 10 CustomerName, SUM(Revenue) as TotalRevenue FROM Sales.Customers GROUP BY CustomerName ORDER BY TotalRevenue DESC",
      "min_confidence": 0.8,
      "description": "Basic aggregation with GROUP BY and ORDER BY"
    }
  ]
}
```

---

### API Function

#### `run_suite()`

Execute regression test suite.

```python
def run_suite(suite_path: str = None) -> Dict[str, Any]:
```

**Returns:**
```python
{
    "summary": {
        "passed": 45,
        "failed": 2,
        "total": 47,
        "pass_rate": 0.957,
        "duration_ms": 5670
    },
    "results": [
        {
            "id": "test_001",
            "prompt": "Show top 10 customers",
            "expected_sql": "SELECT TOP 10...",
            "actual_sql": "SELECT TOP 10...",
            "passed": True,
            "confidence": 0.92,
            "similarity": 0.98,
            "duration_ms": 234
        },
        {
            "id": "test_002",
            "prompt": "Show sales by region",
            "expected_sql": "SELECT Region...",
            "actual_sql": "SELECT Area...",  # Wrong column
            "passed": False,
            "confidence": 0.65,
            "similarity": 0.45,
            "errors": ["Column 'Area' not found"],
            "duration_ms": 189
        }
    ]
}
```

---

### Usage Example

```python
from asklytics_learning_engine.learning import regression

# Run default suite
results = regression.run_suite()

print(f"Pass Rate: {results['summary']['pass_rate']:.1%}")
print(f"Passed: {results['summary']['passed']}/{results['summary']['total']}")

# Show failures
for test in results['results']:
    if not test['passed']:
        print(f"\nFailed: {test['id']}")
        print(f"  Prompt: {test['prompt']}")
        print(f"  Expected: {test['expected_sql']}")
        print(f"  Got: {test['actual_sql']}")
        if test.get('errors'):
            print(f"  Errors: {', '.join(test['errors'])}")
```

---

### Creating Test Suites

```python
import json

test_suite = {
    "version": "1.0",
    "description": "Sales analytics regression tests",
    "tests": [
        {
            "id": "sales_001",
            "prompt": "Show total sales by region",
            "expected_sql": "SELECT Region, SUM(SalesAmount) as TotalSales FROM Sales GROUP BY Region",
            "min_confidence": 0.8,
            "tags": ["aggregation", "group-by"]
        },
        {
            "id": "sales_002",
            "prompt": "Top 5 products by profit margin",
            "expected_sql": "SELECT TOP 5 ProductName, (Revenue - Cost) / Revenue as ProfitMargin FROM Products ORDER BY ProfitMargin DESC",
            "min_confidence": 0.85,
            "tags": ["top-n", "calculated-field"]
        }
    ]
}

with open("data/regression/sales_tests.json", "w") as f:
    json.dump(test_suite, f, indent=2)

# Run custom suite
results = regression.run_suite("data/regression/sales_tests.json")
```

---

## Embeddings & Retrieval

### Module: `asklytics_learning_engine/learning/embedder.py`

### Embedder Model

**Model:** BAAI/bge-m3 (BGE-M3)
- **Dimension:** 1024
- **Context Length:** 8192 tokens
- **Languages:** 100+ (multilingual)
- **Performance:** State-of-the-art retrieval

---

### API Functions

#### `embed_text()`

Generate embedding vector for text.

```python
def embed_text(text: str) -> np.ndarray:
    from asklytics_learning_engine.learning import embedder
    
    text = "Show sales by region for Q4 2025"
    vector = embedder.embed_text(text)
    
    print(f"Dimension: {vector.shape}")  # (1024,)
    print(f"Sample values: {vector[:5]}")
```

---

#### `embed_batch()`

Efficiently embed multiple texts.

```python
def embed_batch(texts: List[str]) -> np.ndarray:
    texts = [
        "Show top customers",
        "Revenue by region",
        "Product inventory levels"
    ]
    
    vectors = embedder.embed_batch(texts)
    print(f"Shape: {vectors.shape}")  # (3, 1024)
```

---

### Similarity Search

```python
import numpy as np
from asklytics_learning_engine.learning import embedder

# Embed queries
query1 = embedder.embed_text("Show sales by region")
query2 = embedder.embed_text("Display revenue per area")
query3 = embedder.embed_text("List all employees")

# Compute cosine similarity
def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

sim_12 = cosine_similarity(query1, query2)
sim_13 = cosine_similarity(query1, query3)

print(f"Similarity (sales by region vs revenue per area): {sim_12:.3f}")  # ~0.85
print(f"Similarity (sales by region vs list employees): {sim_13:.3f}")    # ~0.32
```

---

## Performance Optimization

### FAISS Index Optimization

#### 1. Use IVF for Large Datasets

```python
import faiss

# For > 100K experiences, use IVF index
dim = 1024
nlist = 100  # Number of clusters

# Create IVF index
quantizer = faiss.IndexFlatIP(dim)
index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)

# Train on sample data
sample_vectors = np.random.random((10000, dim)).astype('float32')
faiss.normalize_L2(sample_vectors)
index.train(sample_vectors)

# Add vectors
index.add(sample_vectors)

# Search with probe parameter
index.nprobe = 10  # Search 10 clusters (speed/accuracy trade-off)
distances, indices = index.search(query_vec, k=5)
```

---

#### 2. Batch Operations

```python
# BAD - Individual adds (slow)
for xp_id in xp_ids:
    faiss_updater.add_example(xp_id)

# GOOD - Batch add (fast)
vectors = []
ids = []
for xp_id in xp_ids:
    exp = xp.get_by_id(xp_id)
    vec = embedder.embed_text(exp.user_prompt)
    vectors.append(vec)
    ids.append(xp_id)

vectors = np.vstack(vectors).astype('float32')
faiss.normalize_L2(vectors)
index.add_with_ids(vectors, np.array(ids, dtype='int64'))
```

---

### Database Optimization

#### 1. Index Critical Columns

```sql
-- Experience store
CREATE INDEX IF NOT EXISTS idx_xp_timestamp ON xp(timestamp);
CREATE INDEX IF NOT EXISTS idx_xp_score ON xp(score);
CREATE INDEX IF NOT EXISTS idx_xp_feedback ON xp(feedback);

-- Feedback
CREATE INDEX IF NOT EXISTS idx_feedback_xp ON feedback(xp_id);
CREATE INDEX IF NOT EXISTS idx_feedback_ts ON feedback(ts);
CREATE INDEX IF NOT EXISTS idx_feedback_verdict ON feedback(verdict);
```

---

#### 2. Query Optimization

```python
# BAD - Fetch all then filter
experiences = xp.fetch_all_experiences()
high_conf = [exp for exp in experiences if exp.confidence_score >= 0.8]

# GOOD - Filter in SQL
with xp._conn() as con:
    rows = con.execute(
        "SELECT * FROM xp WHERE confidence_score >= 0.8 ORDER BY timestamp DESC"
    ).fetchall()
```

---

#### 3. Connection Pooling

```python
from contextlib import contextmanager
import sqlite3

class ConnectionPool:
    def __init__(self, db_path, pool_size=5):
        self.db_path = db_path
        self.pool = [sqlite3.connect(db_path) for _ in range(pool_size)]
        self.available = self.pool.copy()
    
    @contextmanager
    def get_connection(self):
        if not self.available:
            # Create temporary connection
            conn = sqlite3.connect(self.db_path)
        else:
            conn = self.available.pop()
        
        try:
            yield conn
        finally:
            if conn in self.pool:
                self.available.append(conn)
            else:
                conn.close()

# Usage
pool = ConnectionPool("learning_store.db")

with pool.get_connection() as conn:
    # Use connection
    pass
```

---

### Caching Strategies

#### 1. LRU Cache for Embeddings

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_embed(text: str) -> bytes:
    """Cache embeddings for repeated queries."""
    vec = embedder.embed_text(text)
    return vec.tobytes()

# Usage
vec_bytes = cached_embed("Show sales by region")
vec = np.frombuffer(vec_bytes, dtype='float32')
```

---

#### 2. Validation Result Cache

```python
from cachetools import TTLCache
import hashlib

# Cache validation results for 5 minutes
validation_cache = TTLCache(maxsize=100, ttl=300)

def validate_with_cache(sql: str, prompt: str) -> dict:
    # Create cache key
    key = hashlib.md5(f"{sql}:{prompt}".encode()).hexdigest()
    
    if key in validation_cache:
        return validation_cache[key]
    
    # Validate
    signals = validator.validate(sql, prompt, schema, conn)
    validation_cache[key] = signals
    
    return signals
```

---

## Monitoring & Metrics

### Learning Health Check

```python
from asklytics_learning_engine.learning import experience_store as xp
import faiss

def learning_health_check():
    """Comprehensive health check for learning system."""
    health = {
        "status": "healthy",
        "components": {}
    }
    
    # Experience store
    try:
        xp_count = xp.count_experiences()
        health["components"]["experience_store"] = {
            "status": "healthy",
            "count": xp_count
        }
    except Exception as e:
        health["components"]["experience_store"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # FAISS index
    try:
        index = faiss.read_index("asklytics_learning_engine/data/faiss_index.faiss")
        health["components"]["faiss_index"] = {
            "status": "healthy",
            "size": index.ntotal
        }
    except Exception as e:
        health["components"]["faiss_index"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Feedback system
    try:
        from asklytics_learning_engine.learning import feedback_dao
        summary = feedback_dao.summary(days=30)
        health["components"]["feedback"] = {
            "status": "healthy",
            "accuracy": summary["accuracy"],
            "total": summary["total"]
        }
    except Exception as e:
        health["components"]["feedback"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Overall status
    if any(c["status"] == "unhealthy" for c in health["components"].values()):
        health["status"] = "degraded"
    
    return health

# Usage
health = learning_health_check()
print(f"Overall: {health['status']}")
for component, status in health['components'].items():
    print(f"  {component}: {status['status']}")
```

---

## Troubleshooting

### FAISS Index Issues

**Problem:** "Index is empty" error

**Solution:**
```python
# Check if index exists and has entries
import faiss
import json

index_path = "asklytics_learning_engine/data/faiss_index.faiss"
meta_path = "asklytics_learning_engine/data/meta.json"

try:
    index = faiss.read_index(index_path)
    print(f"Index size: {index.ntotal}")
    
    with open(meta_path) as f:
        meta = json.load(f)
    print(f"Meta IDs: {len(meta['ids'])}")
    
    if index.ntotal == 0:
        print("Index is empty. Rebuild with:")
        print("  POST /api/faiss/reload")
except FileNotFoundError:
    print("Index files not found. Create with:")
    print("  POST /api/faiss/reload")
```

---

### Low Confidence Scores

**Problem:** Queries consistently return low confidence

**Causes & Solutions:**

1. **Insufficient training data**
   ```python
   # Check experience count
   count = xp.count_experiences()
   if count < 50:
       print("Add more training examples!")
   ```

2. **Poor schema metadata**
   ```python
   # Verify schema is loaded
   from asklytics_learning_engine.learning import validation_rules
   schema = validation_rules.load_schema_metadata()
   print(f"Tables in schema: {len(schema.get('tables', []))}")
   ```

3. **Validation timeout**
   ```python
   # Increase timeout for shadow execution
   cursor.execute(sql, timeout=60)  # 60 seconds
   ```

---

### Feedback Not Improving Results

**Problem:** User feedback isn't improving query quality

**Checks:**

1. **Verify feedback is being stored**
   ```python
   from asklytics_learning_engine.learning import feedback_dao
   recent = feedback_dao.list_feedback(limit=10)
   print(f"Recent feedback: {len(recent)}")
   ```

2. **Check FAISS updates**
   ```python
   # Verify retrain_used flag
   for fb in recent:
       if fb['verdict'] == 'correct' and not fb['retrain_used']:
           print(f"Feedback {fb['id']} not used for retraining!")
   ```

3. **Rebuild index**
   ```bash
   curl -X POST http://localhost:5000/api/faiss/reload
   ```

---

*Last Updated: October 30, 2025*
*Learning Engine Version: 1.0.0*


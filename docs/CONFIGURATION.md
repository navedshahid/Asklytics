# Configuration Guide

Complete guide to configuring and deploying AskLytics.

## Table of Contents

- [Environment Setup](#environment-setup)
- [Database Configuration](#database-configuration)
- [Model Configuration](#model-configuration)
- [Inference Modes](#inference-modes)
- [Governance Settings](#governance-settings)
- [Learning System](#learning-system)
- [Performance Tuning](#performance-tuning)
- [Production Deployment](#production-deployment)

---

## Environment Setup

### Prerequisites

- Python 3.10 or higher
- 8GB RAM minimum (16GB recommended)
- SQL Server 2016+ or compatible database
- Optional: NVIDIA GPU for local LLM (CUDA 11.8+)

---

### Installation

```bash
# Clone repository
git clone https://github.com/your-org/asklytics.git
cd asklytics

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

### Environment Variables

Create `.env` file in project root:

```bash
# === Database Configuration ===
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_SERVER=localhost
DB_DATABASE=AdventureWorks
DB_UID=sa
DB_PWD=YourSecurePassword123!

# === LLM Configuration ===
# Local Model
MODEL_PATH=./models/sqlcoder-7b-2.q8_0.gguf
MODEL_GPU_LAYERS=0  # 0 for CPU, 35 for GPU

# Gemini API
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_MODEL_FOR_SQL=gemini-1.5-flash-latest
GEMINI_BASE_API_URL=https://generativelanguage.googleapis.com/v1beta/models

# === Application Settings ===
FLASK_ENV=development
FLASK_DEBUG=True
ASKLYTICS_INFERENCE=gemini  # local, gemini, or gpt

# === Learning System ===
LEARN_DB_URL=sqlite:///./learning_store.db
CHAT_SESSION_LIMIT=5

# === Governance ===
MASKING_ENABLED=true
AUDIT_RETENTION_DAYS=90
AUDIT_DB_PATH=./data/audit.db

# === Paths ===
GENDS_CONFIG_DIR=./data
```

---

### Directory Structure

```
asklytics/
├── app.py                          # Main Flask application
├── .env                            # Environment variables (create this)
├── requirements.txt                # Python dependencies
├── data/                           # Runtime data
│   ├── asklytics_config.json      # Persistent config
│   ├── audit.db                   # Audit logs
│   └── threads.json               # Conversation threads
├── models/                        # LLM models
│   └── sqlcoder-7b-2.q8_0.gguf   # SQLCoder model
├── asklytics_learning_engine/    # Learning system
│   ├── data/
│   │   ├── faiss_index.faiss     # Vector index
│   │   ├── meta.json             # Index metadata
│   │   └── schema.json           # Cached schema
│   └── learning/                 # Learning modules
├── governance/                    # Security & compliance
│   ├── rbac.py
│   ├── masker.py
│   └── routes.py
├── templates/                     # HTML templates
│   ├── index.html
│   ├── settings.html
│   └── dashboard.html
├── static/                        # Static assets
│   ├── css/
│   └── js/
└── docs/                          # Documentation
```

---

## Database Configuration

### Supported Databases

- Microsoft SQL Server 2016+
- Azure SQL Database
- SQL Server on Linux
- Compatible with: D365 Finance & Operations

---

### Connection Configuration

#### Method 1: Environment Variables (.env)

```bash
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_SERVER=localhost
DB_DATABASE=AdventureWorks
DB_UID=sa
DB_PWD=YourPassword123
```

#### Method 2: UI Settings Page

1. Navigate to `http://localhost:5000/settings`
2. Enter database credentials
3. Click "Test Connection"
4. Click "Save Configuration"

#### Method 3: API

```bash
curl -X POST http://localhost:5000/api/settings/db/save \
  -H "Content-Type: application/json" \
  -d '{
    "server": "localhost",
    "database": "AdventureWorks",
    "uid": "sa",
    "pwd": "YourPassword123",
    "driver": "ODBC Driver 17 for SQL Server"
  }'
```

---

### Connection String Format

AskLytics uses ODBC connection strings:

```
DRIVER={ODBC Driver 17 for SQL Server};
SERVER=hostname;
DATABASE=dbname;
UID=username;
PWD=password;
TrustServerCertificate=yes;
```

---

### Azure SQL Database

```bash
# .env
DB_SERVER=myserver.database.windows.net
DB_DATABASE=mydb
DB_UID=adminuser@myserver
DB_PWD=YourPassword123
```

Connection string:
```
DRIVER={ODBC Driver 17 for SQL Server};
SERVER=myserver.database.windows.net;
DATABASE=mydb;
UID=adminuser@myserver;
PWD=YourPassword123;
Encrypt=yes;
TrustServerCertificate=no;
```

---

### Connection Pooling

Configure pool size in `app.py`:

```python
# app.py
connection_pool = ConnectionPool(size=5)  # Default: 5 connections
```

Adjust based on concurrent users:
- **5-10 users:** pool_size=5
- **10-50 users:** pool_size=10
- **50+ users:** pool_size=20

---

### Table Selection

After connecting, select tables to include in schema context:

```python
# Via API
curl -X POST http://localhost:5000/api/settings/tables/save \
  -H "Content-Type: application/json" \
  -d '{
    "tables": [
      "Sales.SalesOrderHeader",
      "Sales.SalesOrderDetail",
      "Production.Product",
      "Sales.Customer"
    ]
  }'
```

Or use the UI Settings page.

---

## Model Configuration

### Local Model (SQLCoder-7B)

#### Download Model

```bash
# Create models directory
mkdir -p models

# Download SQLCoder-7B Q8 (8GB)
wget https://huggingface.co/TheBloke/sqlcoder-7b-2-GGUF/resolve/main/sqlcoder-7b-2.q8_0.gguf \
  -O models/sqlcoder-7b-2.q8_0.gguf
```

#### Configuration

```bash
# .env
MODEL_PATH=./models/sqlcoder-7b-2.q8_0.gguf
MODEL_GPU_LAYERS=0  # CPU mode

# For GPU acceleration (requires CUDA)
MODEL_GPU_LAYERS=35  # Offload all layers to GPU
```

#### Memory Requirements

| Quantization | RAM | Quality |
|--------------|-----|---------|
| Q4_K_M | 4GB | Good |
| Q5_K_M | 5GB | Better |
| Q8_0 | 8GB | Best |

---

### Embedder Model

AskLytics uses BAAI/bge-m3 for semantic search.

#### Configuration

```python
# app.py (auto-configured)
embedder = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
```

#### GPU Acceleration

```python
# Enable GPU for embedder
embedder = BGEM3FlagModel(
    'BAAI/bge-m3',
    use_fp16=True,
    device='cuda'  # Use GPU
)
```

#### Memory Requirements

- **CPU:** 2GB RAM
- **GPU:** 1GB VRAM

---

### Model Selection Strategy

| Scenario | Recommended Model |
|----------|------------------|
| No GPU, local-only | SQLCoder-7B Q4 (CPU) |
| GPU available | SQLCoder-7B Q8 (GPU) |
| API available, fast queries | Gemini 1.5 Flash |
| Maximum accuracy | Gemini + SQLCoder hybrid |
| Large-scale production | GPT-OSS-20B (vLLM) |

---

## Inference Modes

### Mode 1: Local (SQLCoder)

**Pros:**
- No API costs
- Data stays on-premise
- No internet required

**Cons:**
- Requires local GPU for best performance
- Slower than cloud APIs
- 8GB+ RAM required

**Configuration:**
```bash
# .env
ASKLYTICS_INFERENCE=local
MODEL_PATH=./models/sqlcoder-7b-2.q8_0.gguf
MODEL_GPU_LAYERS=0
```

---

### Mode 2: Gemini (Cloud)

**Pros:**
- Fast inference (< 1 second)
- No local compute needed
- Highly accurate

**Cons:**
- Requires API key
- Per-token costs
- Data leaves premises

**Configuration:**
```bash
# .env
ASKLYTICS_INFERENCE=gemini
GEMINI_API_KEY=your-api-key-here
GEMINI_MODEL_FOR_SQL=gemini-1.5-flash-latest
```

**Get API Key:**
1. Visit https://makersuite.google.com/app/apikey
2. Create new API key
3. Add to `.env`

**Pricing:** ~$0.000002 per token (very low cost)

---

### Mode 3: Hybrid (Gemini + SQLCoder)

**Pros:**
- Best accuracy
- SQLCoder validates/repairs Gemini output
- Automatic fallback

**Cons:**
- Requires both models configured
- Slightly slower

**Configuration:**
```bash
# .env
ASKLYTICS_INFERENCE=gemini  # Primary
MODEL_PATH=./models/sqlcoder-7b-2.q8_0.gguf  # Fallback/validator
GEMINI_API_KEY=your-api-key-here
```

---

### Mode 4: GPT-OSS (vLLM)

**Pros:**
- Production-scale serving
- Batch processing
- High throughput

**Cons:**
- Requires separate vLLM server
- Complex setup
- GPU required

**Configuration:**

1. **Start vLLM server:**
```bash
python -m vllm.entrypoints.openai.api_server \
  --model gpt-oss-20b \
  --tensor-parallel-size 2 \
  --host 0.0.0.0 \
  --port 8000
```

2. **Configure AskLytics:**
```json
// data/asklytics_config.json
{
  "gpt": {
    "base_url": "http://localhost:8000/v1",
    "model": "gpt-oss-20b"
  }
}
```

---

### Switching Inference Modes

#### Via UI

1. Go to Settings → Inference Mode
2. Select mode
3. Click Save

#### Via API

```bash
curl -X POST http://localhost:5000/api/settings/inference \
  -H "Content-Type: application/json" \
  -d '{"mode": "gemini"}'
```

#### Via Code

```python
config.set_inference_mode("gemini")
```

---

## Governance Settings

### Masking Configuration

#### Default Behavior

PII is masked by default for all users except those with `pii_viewer` role.

#### Policy Configuration

```python
# governance/masker.py
from governance import MaskingPolicy

policy = MaskingPolicy(
    pii_columns={
        "Sales.Customer": ["CustomerName", "EmailAddress", "Phone"],
        "HumanResources.Employee": ["FirstName", "LastName", "SSN", "BirthDate"]
    },
    mask_token="***",
    preserve_nulls=True,
    additional_keywords={"internal_notes", "comments"}
)
```

---

### Audit Configuration

```bash
# .env
AUDIT_DB_PATH=./data/audit.db
AUDIT_RETENTION_DAYS=90
```

#### Retention Policy

```python
# Nightly cleanup (runs automatically)
# Or manual:
curl -X POST http://localhost:5000/api/learn/cleanup \
  -H "Content-Type: application/json" \
  -d '{"days": 90}'
```

---

### Role Configuration

Edit `governance/rbac.py`:

```python
# Add custom roles
PII_VIEWER_ROLES = {
    "pii_viewer",
    "auditor",
    "admin",
    "security",
    "compliance_officer"  # Add custom role
}
```

---

## Learning System

### Experience Store

```bash
# .env
LEARN_DB_URL=sqlite:///./learning_store.db
```

For production with PostgreSQL:
```bash
LEARN_DB_URL=postgresql://user:password@localhost:5432/asklytics_learn
```

---

### FAISS Index Configuration

```python
# asklytics_learning_engine/learning/embedder.py
DATA_DIR = "asklytics_learning_engine/data"
INDEX_PATH = os.path.join(DATA_DIR, "faiss_index.faiss")
META_PATH = os.path.join(DATA_DIR, "meta.json")
```

#### Index Parameters

```python
# For small datasets (< 10K)
index = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))

# For large datasets (> 100K)
nlist = 100  # Number of clusters
index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
index.nprobe = 10  # Search clusters
```

---

### Feedback Thresholds

```python
# feedback_manager.py
CONFIDENCE_THRESHOLD = 0.7  # Minimum confidence to add to index
AUTO_INDEX_ENABLED = True   # Automatically index correct feedback
```

---

### Regression Testing

```bash
# Configure test suite location
REGRESSION_SUITE_PATH=./data/regression/default.json
```

Schedule automated tests:
```bash
# Run daily via cron
0 2 * * * curl -X POST http://localhost:5000/api/learn/regression/run
```

---

## Performance Tuning

### Database Connection Pool

```python
# app.py
connection_pool = ConnectionPool(size=10)  # Increase for more users
```

**Guidelines:**
- 1 connection per 5-10 concurrent users
- Max: 20-25 connections (SQL Server license limits)

---

### Query Timeout

```python
# app.py
def _safe_execute_sql(cursor, sql, timeout_seconds=30):
    cursor.execute(sql)  # Timeout handled by connection string
```

Set in connection string:
```
...;Connection Timeout=30;...
```

---

### LLM Context Window

```python
# app.py
config = {
    "llm": {
        "n_ctx": 8096,  # Context window size
        "n_threads": 8   # CPU threads
    }
}
```

Adjust based on hardware:
- **4-core CPU:** n_threads=4
- **8-core CPU:** n_threads=8
- **GPU mode:** n_threads=4 (GPU does heavy lifting)

---

### FAISS Search Performance

```python
# Adjust k (number of similar examples)
similar = retrieve_examples(prompt, k=5)  # Default
similar = retrieve_examples(prompt, k=3)  # Faster, less context
```

---

### Caching

#### Response Caching

```python
from cachetools import TTLCache

# Cache validation results
validation_cache = TTLCache(maxsize=100, ttl=300)  # 5 minutes
```

#### Static Asset Caching

```python
# app.py
@app.after_request
def add_cache_headers(response):
    if request.path.startswith('/static/'):
        response.cache_control.max_age = 86400  # 24 hours
    return response
```

---

## Production Deployment

### Using Waitress (Windows/Linux)

```python
# app.py (already configured)
if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=5000, threads=8)
```

Start server:
```bash
python app.py
```

---

### Using Gunicorn (Linux)

```bash
pip install gunicorn

gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 app:app
```

---

### Systemd Service (Linux)

Create `/etc/systemd/system/asklytics.service`:

```ini
[Unit]
Description=AskLytics SQL Analytics Service
After=network.target

[Service]
Type=simple
User=asklytics
WorkingDirectory=/opt/asklytics
Environment="PATH=/opt/asklytics/.venv/bin"
ExecStart=/opt/asklytics/.venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable asklytics
sudo systemctl start asklytics
sudo systemctl status asklytics
```

---

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    unixodbc \
    unixodbc-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install ODBC Driver
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17

# Copy application
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Download model (if using local)
RUN mkdir -p models && \
    wget https://huggingface.co/TheBloke/sqlcoder-7b-2-GGUF/resolve/main/sqlcoder-7b-2.q8_0.gguf \
    -O models/sqlcoder-7b-2.q8_0.gguf

EXPOSE 5000

CMD ["python", "app.py"]
```

Build and run:
```bash
docker build -t asklytics .
docker run -p 5000:5000 -v $(pwd)/data:/app/data asklytics
```

---

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  asklytics:
    build: .
    ports:
      - "5000:5000"
    environment:
      - DB_SERVER=sqlserver
      - DB_DATABASE=AdventureWorks
      - DB_UID=sa
      - DB_PWD=YourPassword123
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - ASKLYTICS_INFERENCE=gemini
    volumes:
      - ./data:/app/data
      - ./models:/app/models
    depends_on:
      - sqlserver
    restart: unless-stopped

  sqlserver:
    image: mcr.microsoft.com/mssql/server:2022-latest
    environment:
      - ACCEPT_EULA=Y
      - SA_PASSWORD=YourPassword123
    ports:
      - "1433:1433"
    volumes:
      - sqlserver-data:/var/opt/mssql

volumes:
  sqlserver-data:
```

Start:
```bash
export GEMINI_API_KEY=your-key-here
docker-compose up -d
```

---

### Nginx Reverse Proxy

```nginx
# /etc/nginx/sites-available/asklytics
server {
    listen 80;
    server_name asklytics.example.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # SSE support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }

    location /static/ {
        alias /opt/asklytics/static/;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable:
```bash
sudo ln -s /etc/nginx/sites-available/asklytics /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

### HTTPS with Let's Encrypt

```bash
sudo apt-get install certbot python3-certbot-nginx

sudo certbot --nginx -d asklytics.example.com
```

Auto-renewal:
```bash
sudo certbot renew --dry-run
```

---

### Health Monitoring

```bash
# Healthcheck endpoint
curl http://localhost:5000/api/health/full

# Prometheus metrics (if enabled)
curl http://localhost:5000/metrics
```

Add to monitoring:
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'asklytics'
    static_configs:
      - targets: ['localhost:5000']
    metrics_path: '/metrics'
```

---

### Backup Strategy

#### 1. Database Backups

```bash
# Backup learning database
sqlite3 learning_store.db ".backup learning_store_backup.db"

# Backup audit database
sqlite3 data/audit.db ".backup data/audit_backup.db"
```

#### 2. Configuration Backups

```bash
# Backup config and data
tar -czf asklytics-backup-$(date +%Y%m%d).tar.gz \
  data/ \
  models/ \
  .env \
  asklytics_learning_engine/data/
```

#### 3. Automated Backups

```bash
# Add to crontab
0 2 * * * /opt/asklytics/scripts/backup.sh
```

---

### Scaling Considerations

#### Vertical Scaling

| Users | CPU | RAM | Storage |
|-------|-----|-----|---------|
| 1-10 | 2 cores | 8GB | 50GB |
| 10-50 | 4 cores | 16GB | 100GB |
| 50-200 | 8 cores | 32GB | 250GB |
| 200+ | 16+ cores | 64GB+ | 500GB+ |

#### Horizontal Scaling

For > 200 concurrent users:

1. **Load Balancer** (Nginx/HAProxy)
2. **Multiple App Instances**
3. **Shared Storage** (NFS/S3)
4. **Centralized Database** (PostgreSQL)
5. **Redis Cache** (shared session state)

---

### Security Hardening

#### 1. Change Default Secrets

```bash
# Generate secure secret key
python -c "import secrets; print(secrets.token_hex(32))"

# Add to .env
SECRET_KEY=your-generated-secret-here
```

#### 2. Firewall Rules

```bash
# Allow only necessary ports
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

#### 3. Rate Limiting

```python
# app.py
from flask_limiter import Limiter

limiter = Limiter(
    app,
    key_func=lambda: request.headers.get('X-User-ID', 'anonymous'),
    default_limits=["100 per minute"]
)

@app.route("/api/ask/stream")
@limiter.limit("10 per minute")
def ask_stream():
    # ...
```

#### 4. Environment Variables

Never commit `.env` to version control:

```bash
# .gitignore
.env
*.db
models/
```

---

## Troubleshooting

### Common Issues

#### 1. "ODBC Driver not found"

**Solution:**
```bash
# Windows
# Download from: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

# Linux
sudo apt-get install unixodbc unixodbc-dev
curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list > /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install msodbcsql17
```

#### 2. "Model file not found"

**Solution:**
```bash
# Download SQLCoder model
mkdir -p models
wget https://huggingface.co/TheBloke/sqlcoder-7b-2-GGUF/resolve/main/sqlcoder-7b-2.q8_0.gguf \
  -O models/sqlcoder-7b-2.q8_0.gguf
```

#### 3. "Out of memory" when loading model

**Solution:**
Use smaller quantization:
```bash
# Q4 (4GB) instead of Q8 (8GB)
wget https://huggingface.co/TheBloke/sqlcoder-7b-2-GGUF/resolve/main/sqlcoder-7b-2.Q4_K_M.gguf \
  -O models/sqlcoder-7b-2.q4.gguf

# Update .env
MODEL_PATH=./models/sqlcoder-7b-2.q4.gguf
```

#### 4. "FAISS index not found"

**Solution:**
```bash
# Rebuild index
curl -X POST http://localhost:5000/api/faiss/reload
```

---

*Last Updated: October 30, 2025*
*Configuration Guide Version: 1.0.0*


# AskLytics Documentation

Complete documentation for the AskLytics intelligent SQL analytics platform.

## 📚 Documentation Index

### Getting Started

- **[Getting Started Guide](./GETTING_STARTED.md)** - Quick setup and first steps
  - 5-minute quick start
  - Complete setup tutorial
  - Your first query
  - Usage examples
  - Common workflows

### Core Documentation

- **[API Reference](./API_REFERENCE.md)** - Complete REST API documentation
  - All 75+ API endpoints documented
  - Request/response formats
  - Authentication & authorization
  - **Metadata Management** (harvest, search, BKG export)
  - Code examples (Python, JavaScript, cURL)
  - Error handling
  - Rate limiting

- **[Configuration Guide](./CONFIGURATION.md)** - Setup and configuration
  - Environment setup
  - Database configuration
  - Model configuration
  - Inference modes (Local, Gemini, GPT)
  - Performance tuning
  - Production deployment

- **[Governance Module](./GOVERNANCE_MODULE.md)** - Security and compliance
  - RBAC (Role-Based Access Control)
  - PII masking and unmasking
  - Audit logging
  - ISO 27001 compliance
  - GDPR alignment
  - Security best practices

- **[Learning Engine](./LEARNING_ENGINE.md)** - AI learning system
  - Experience store
  - FAISS vector index
  - Hybrid validator
  - Feedback system
  - Regression testing
  - Performance optimization

## 🎯 Quick Navigation

### I want to...

**Get started quickly**
→ [Getting Started](./GETTING_STARTED.md#quick-start-5-minutes)

**Integrate with my app**
→ [API Reference](./API_REFERENCE.md)

**Deploy to production**
→ [Configuration - Production Deployment](./CONFIGURATION.md#production-deployment)

**Secure my data**
→ [Governance Module](./GOVERNANCE_MODULE.md)

**Improve accuracy**
→ [Learning Engine](./LEARNING_ENGINE.md)

**Harvest database metadata**
→ [API Reference - Metadata Management](./API_REFERENCE.md#metadata-management)

**Troubleshoot issues**
→ [Configuration - Troubleshooting](./CONFIGURATION.md#troubleshooting)

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Web UI / API                         │
│                    (index.html / REST API)                   │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                       Flask Application                      │
│                         (app.py)                             │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ Orchestrator │  │  Governance  │  │ Learning Engine │  │
│  │              │  │  - RBAC      │  │ - Experience    │  │
│  │ - Query      │  │  - Masking   │  │ - FAISS Index   │  │
│  │ - Execute    │  │  - Audit     │  │ - Feedback      │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                             │
                   ┌─────────┴─────────┐
                   ▼                   ▼
         ┌──────────────────┐  ┌──────────────┐
         │   LLM Providers  │  │   Database   │
         │                  │  │              │
         │ - Gemini         │  │ - SQL Server │
         │ - SQLCoder       │  │ - Azure SQL  │
         │ - GPT-OSS        │  │ - D365       │
         └──────────────────┘  └──────────────┘
```

## 🔑 Key Features

### 1. Multi-Model Support
- **Gemini 1.5 Flash** - Fast, cloud-based (recommended)
- **SQLCoder-7B** - Local, private, no API costs
- **GPT-OSS-20B** - Production scale via vLLM
- **Hybrid Mode** - Gemini + SQLCoder validation

### 2. Self-Learning System
- User feedback improves results
- FAISS-powered semantic retrieval
- Automated regression testing
- Confidence scoring

### 3. Enterprise Security
- Role-based access control (RBAC)
- Automatic PII masking
- Comprehensive audit logging
- ISO 27001 / GDPR / SOC 2 aligned

### 4. Developer-Friendly
- RESTful API with SSE streaming
- Python, JavaScript SDKs
- Comprehensive documentation
- Docker deployment ready

## 📖 Documentation Structure

```
docs/
├── README.md                    # This file - documentation index
├── GETTING_STARTED.md          # Quick start and tutorials
├── API_REFERENCE.md            # Complete API documentation
├── CONFIGURATION.md            # Setup and configuration
├── GOVERNANCE_MODULE.md        # Security and compliance
└── LEARNING_ENGINE.md          # AI learning system
```

## 🚀 Quick Start

### 1. Install

```bash
git clone https://github.com/your-org/asklytics.git
cd asklytics
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cat > .env <<EOF
GEMINI_API_KEY=your-api-key-here
ASKLYTICS_INFERENCE=gemini
DB_SERVER=localhost
DB_DATABASE=AdventureWorks
DB_UID=sa
DB_PWD=YourPassword123
EOF
```

### 3. Run

```bash
python app.py
```

Visit: http://localhost:5000

### 4. Ask

```
Show me the top 10 customers by revenue
```

Done! 🎉

## 💡 Common Use Cases

### Sales Analytics
```
"Show monthly sales trend for the last 12 months"
"Who are our top customers by lifetime value?"
"Compare Q4 sales to last year"
```

### Customer Insights
```
"Show customer retention rate by cohort"
"What's the average order value by customer segment?"
"How many new customers did we acquire this month?"
```

### Inventory Management
```
"Show products below reorder point"
"What are the top 20 fastest moving items?"
"Show inventory levels by warehouse"
```

### Financial Reporting
```
"Show revenue by department"
"Calculate profit margins by product category"
"Compare actual vs budget for Q4"
```

## 🔧 API Examples

### Python

```python
import requests

response = requests.post(
    "http://localhost:5000/api/gemini_ask/stream",
    headers={"Content-Type": "application/json"},
    json={"question": "Show sales by region"},
    stream=True
)

for line in response.iter_lines():
    if line.startswith(b'data: '):
        print(line[6:].decode())
```

### JavaScript

```javascript
const response = await fetch('/api/gemini_ask/stream', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({question: 'Show sales by region'})
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    console.log(decoder.decode(value));
}
```

### cURL

```bash
curl -X POST http://localhost:5000/api/gemini_ask/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "Show sales by region"}'
```

## 📊 Governance Dashboard

Access compliance and audit features:

```
http://localhost:5000/dashboard
```

**Features:**
- Real-time query monitoring
- PII exposure tracking
- Confidence score trends
- User feedback analytics
- Audit log export

## 🎓 Learning Resources

### Tutorials
- [Quick Start (5 minutes)](./GETTING_STARTED.md#quick-start-5-minutes)
- [Complete Setup Tutorial](./GETTING_STARTED.md#complete-setup-tutorial)
- [Your First Query](./GETTING_STARTED.md#your-first-query)
- [Common Workflows](./GETTING_STARTED.md#common-workflows)

### API Guides
- [Authentication & Authorization](./API_REFERENCE.md#authentication--authorization)
- [Core Query APIs](./API_REFERENCE.md#core-query-apis)
- [Feedback System](./API_REFERENCE.md#feedback)
- [Error Handling](./API_REFERENCE.md#error-handling)

### Configuration
- [Database Setup](./CONFIGURATION.md#database-configuration)
- [Model Configuration](./CONFIGURATION.md#model-configuration)
- [Inference Modes](./CONFIGURATION.md#inference-modes)
- [Production Deployment](./CONFIGURATION.md#production-deployment)

### Security
- [RBAC Setup](./GOVERNANCE_MODULE.md#rbac-role-based-access-control)
- [PII Masking](./GOVERNANCE_MODULE.md#pii-masking)
- [Audit Logging](./GOVERNANCE_MODULE.md#audit-logging)
- [Compliance Features](./GOVERNANCE_MODULE.md#compliance-features)

### AI/ML
- [Experience Store](./LEARNING_ENGINE.md#experience-store)
- [FAISS Index](./LEARNING_ENGINE.md#faiss-vector-index)
- [Feedback System](./LEARNING_ENGINE.md#feedback-system)
- [Regression Testing](./LEARNING_ENGINE.md#regression-testing)

## 🔒 Security & Compliance

### Supported Standards

| Standard | Coverage |
|----------|----------|
| ISO 27001 | ✅ Access control, audit logging, data protection |
| GDPR | ✅ PII masking, right to privacy, data minimization |
| SOC 2 | ✅ Security, availability, confidentiality |
| HIPAA | ⚠️ Partial - requires additional configuration |

### Security Features

- **Authentication:** Header-based role resolution
- **Authorization:** Role-based access control (RBAC)
- **PII Protection:** Automatic masking with controlled unmasking
- **Audit Trails:** Comprehensive logging of all actions
- **Data Encryption:** TLS/SSL for transport, encrypted at rest
- **Session Management:** Secure session tracking

## 🛠️ Troubleshooting

### Common Issues

**Problem:** "ODBC Driver not found"
→ [Configuration - Troubleshooting](./CONFIGURATION.md#common-issues)

**Problem:** "Model file not found"
→ [Configuration - Model Setup](./CONFIGURATION.md#local-model-sqlcoder-7b)

**Problem:** "Low confidence scores"
→ [Learning Engine - Troubleshooting](./LEARNING_ENGINE.md#low-confidence-scores)

**Problem:** "PII still visible"
→ [Governance - Troubleshooting](./GOVERNANCE_MODULE.md#pii-still-visible)

## 📈 Performance

### Benchmarks

| Configuration | Queries/sec | Latency (p95) | Memory |
|---------------|-------------|---------------|--------|
| Gemini API | 50 | 1.2s | 2GB |
| SQLCoder CPU | 5 | 8.5s | 8GB |
| SQLCoder GPU | 20 | 2.1s | 12GB |
| GPT-OSS vLLM | 100+ | 0.8s | 24GB |

### Optimization

- [Performance Tuning](./CONFIGURATION.md#performance-tuning)
- [Connection Pooling](./CONFIGURATION.md#connection-pooling)
- [FAISS Optimization](./LEARNING_ENGINE.md#performance-optimization)
- [Caching Strategies](./CONFIGURATION.md#caching)

## 🤝 Contributing

We welcome contributions! See our contribution guidelines:

- Report bugs via GitHub Issues
- Submit feature requests
- Contribute code via Pull Requests
- Improve documentation
- Share usage examples

## 📞 Support

### Community Support

- **GitHub Issues:** https://github.com/your-org/asklytics/issues
- **Discussions:** https://github.com/your-org/asklytics/discussions
- **Stack Overflow:** Tag with `asklytics`

### Commercial Support

- **Email:** support@asklytics.com
- **Enterprise Support:** Available for production deployments
- **Training:** Custom training and workshops
- **Consulting:** Architecture and implementation guidance

## 📜 License

AskLytics is released under the MIT License.

## 🙏 Acknowledgments

Built with:
- Flask (Web framework)
- Google Gemini (LLM API)
- SQLCoder (Local LLM)
- FAISS (Vector search)
- BGE-M3 (Embeddings)

## 📝 Changelog

### Version 1.0.0 (October 2025)

**Features:**
- Multi-model LLM support (Gemini, SQLCoder, GPT-OSS)
- Self-learning with FAISS vector search
- Hybrid SQL validation
- RBAC and PII masking
- Comprehensive audit logging
- RESTful API with SSE streaming
- Web UI with Business Mode

**Security:**
- Fixed query parameter role injection vulnerability
- Added resource leak protections
- Improved authorization consistency

**Documentation:**
- Complete API reference
- Configuration guide
- Governance module docs
- Learning engine docs
- Getting started guide

---

## 🎯 Next Steps

1. **[Get Started](./GETTING_STARTED.md)** - Follow the quick start guide
2. **[Explore API](./API_REFERENCE.md)** - Learn the API endpoints
3. **[Configure](./CONFIGURATION.md)** - Set up for your environment
4. **[Secure](./GOVERNANCE_MODULE.md)** - Implement security controls
5. **[Optimize](./LEARNING_ENGINE.md)** - Improve accuracy with learning

---

**Ready to get started?** → [Getting Started Guide](./GETTING_STARTED.md)

*Last Updated: October 30, 2025*
*Documentation Version: 1.0.0*


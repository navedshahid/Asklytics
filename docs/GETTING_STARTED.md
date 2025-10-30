# Getting Started with AskLytics

A step-by-step guide to get up and running with AskLytics in 15 minutes.

## Table of Contents

- [Quick Start (5 minutes)](#quick-start-5-minutes)
- [Complete Setup Tutorial](#complete-setup-tutorial)
- [Your First Query](#your-first-query)
- [Usage Examples](#usage-examples)
- [Common Workflows](#common-workflows)
- [Best Practices](#best-practices)
- [Next Steps](#next-steps)

---

## Quick Start (5 minutes)

### 1. Install Dependencies

```bash
# Clone and setup
git clone https://github.com/your-org/asklytics.git
cd asklytics
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Create .env file
cat > .env <<EOF
GEMINI_API_KEY=your-api-key-here
ASKLYTICS_INFERENCE=gemini
DB_SERVER=localhost
DB_DATABASE=AdventureWorks
DB_UID=sa
DB_PWD=YourPassword123
EOF
```

### 3. Start Server

```bash
python app.py
```

Visit: http://localhost:5000

### 4. First Query

In the UI, type:
```
Show me the top 10 customers by total sales
```

That's it! 🎉

---

## Complete Setup Tutorial

### Step 1: System Requirements

**Check your system:**

```bash
# Python version (need 3.10+)
python --version

# Available memory
free -h  # Linux
wmic OS get TotalVisibleMemorySize  # Windows

# ODBC drivers
odbcinst -j  # Linux
```

**Minimum Requirements:**
- Python 3.10+
- 8GB RAM
- 10GB free disk space
- SQL Server access

---

### Step 2: Get API Keys

#### Option A: Gemini (Recommended for Beginners)

1. Visit https://makersuite.google.com/app/apikey
2. Click "Create API Key"
3. Copy the key

#### Option B: Local Model (No API needed)

Download SQLCoder model:
```bash
mkdir -p models
wget https://huggingface.co/TheBloke/sqlcoder-7b-2-GGUF/resolve/main/sqlcoder-7b-2.q8_0.gguf \
  -O models/sqlcoder-7b-2.q8_0.gguf
```

---

### Step 3: Database Setup

#### If you have SQL Server:

```bash
# Test connection
sqlcmd -S localhost -U sa -P YourPassword123 -Q "SELECT @@VERSION"
```

#### If you don't have SQL Server:

Use Docker:
```bash
docker run -e "ACCEPT_EULA=Y" -e "SA_PASSWORD=YourPassword123!" \
  -p 1433:1433 --name sql1 \
  -d mcr.microsoft.com/mssql/server:2022-latest
```

Restore sample database:
```bash
# Download AdventureWorks
wget https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks/AdventureWorks2019.bak

# Restore
docker cp AdventureWorks2019.bak sql1:/var/opt/mssql/data/
docker exec -it sql1 /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P 'YourPassword123!' \
  -Q "RESTORE DATABASE AdventureWorks FROM DISK='/var/opt/mssql/data/AdventureWorks2019.bak' WITH MOVE 'AdventureWorks' TO '/var/opt/mssql/data/AdventureWorks.mdf', MOVE 'AdventureWorks_Log' TO '/var/opt/mssql/data/AdventureWorks_Log.ldf'"
```

---

### Step 4: Application Setup

#### Create Configuration

```bash
# .env file
cat > .env <<'EOF'
# === Inference Mode ===
ASKLYTICS_INFERENCE=gemini
GEMINI_API_KEY=your-actual-api-key-here

# === Database ===
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_SERVER=localhost
DB_DATABASE=AdventureWorks
DB_UID=sa
DB_PWD=YourPassword123!

# === Models (if using local) ===
MODEL_PATH=./models/sqlcoder-7b-2.q8_0.gguf
MODEL_GPU_LAYERS=0

# === Application ===
FLASK_ENV=development
CHAT_SESSION_LIMIT=5

# === Learning ===
LEARN_DB_URL=sqlite:///./learning_store.db

# === Governance ===
MASKING_ENABLED=true
AUDIT_RETENTION_DAYS=90
EOF
```

---

### Step 5: Initialize Application

```bash
# Install dependencies
pip install -r requirements.txt

# Create data directories
mkdir -p data
mkdir -p asklytics_learning_engine/data

# Start server
python app.py
```

**Expected output:**
```
INFO | GenDS | Loaded config from e:\Personal\AskLytics_MVP\data\asklytics_config.json
INFO | GenDS | Persistent config detected. Activating database connection pool...
INFO | GenDS | Connection pool init: 5/5
INFO | GenDS | Serving on http://0.0.0.0:5000
```

---

### Step 6: Configure via UI

1. **Open Settings:**
   Navigate to http://localhost:5000/settings

2. **Test Database:**
   - Enter credentials
   - Click "Test Connection"
   - Should see "✓ Connection successful"

3. **Save Configuration:**
   - Click "Save Configuration"
   - Wait for "Configuration saved"

4. **Select Tables:**
   - Click "Load Tables"
   - Select relevant tables
   - Click "Save Selection"

5. **Set Inference Mode:**
   - Select "Gemini" (or "Local")
   - Click "Save"

6. **Harvest Metadata (Recommended):**
   ```bash
   # Extract schema metadata for better SQL generation
   curl -X POST http://localhost:5000/api/metadata/harvest \
     -H "Content-Type: application/json" \
     -d '{
       "scope": ["tables", "columns", "foreign_keys", "descriptions"],
       "source": "SqlServer:YourDatabase"
     }'
   ```
   
   **Why harvest?**
   - ✅ LLM learns foreign key relationships
   - ✅ Better table/column suggestions
   - ✅ Validates SQL against actual schema
   - ✅ Includes MS_Description properties
   
   **Takes:** 10-30 seconds for 100 tables
   
   **Optional scopes for more detail:**
   - `row_counts` - Add row count to each table (slower)
   - `samples` - Include sample values per column (slowest)

---

## Your First Query

### Example 1: Simple Aggregation

**Question:**
```
What are the total sales by territory?
```

**Expected SQL:**
```sql
SELECT 
    TerritoryName,
    SUM(SalesAmount) as TotalSales
FROM Sales.SalesOrderHeader soh
JOIN Sales.SalesTerritory st ON soh.TerritoryID = st.TerritoryID
GROUP BY TerritoryName
ORDER BY TotalSales DESC
```

**Result:**
```
Northwest: $2,345,678
Southwest: $1,987,543
Northeast: $1,654,321
...
```

---

### Example 2: Time-based Analysis

**Question:**
```
Show monthly sales trend for the last 12 months
```

**Expected SQL:**
```sql
SELECT 
    FORMAT(OrderDate, 'yyyy-MM') as Month,
    COUNT(*) as OrderCount,
    SUM(TotalDue) as Revenue
FROM Sales.SalesOrderHeader
WHERE OrderDate >= DATEADD(month, -12, GETDATE())
GROUP BY FORMAT(OrderDate, 'yyyy-MM')
ORDER BY Month
```

---

### Example 3: Top N Query

**Question:**
```
Who are the top 10 customers by lifetime value?
```

**Expected SQL:**
```sql
SELECT TOP 10
    c.CustomerID,
    p.FirstName + ' ' + p.LastName as CustomerName,
    SUM(soh.TotalDue) as LifetimeValue
FROM Sales.Customer c
JOIN Person.Person p ON c.PersonID = p.BusinessEntityID
JOIN Sales.SalesOrderHeader soh ON c.CustomerID = soh.CustomerID
GROUP BY c.CustomerID, p.FirstName, p.LastName
ORDER BY LifetimeValue DESC
```

---

## Usage Examples

### Web UI Examples

#### Chat-Style Interaction

```
You: Show sales by region
AI: [Generates SQL and executes]
    Here are the sales by region...

You: Now filter to only Q4
AI: [Refines previous SQL]
    Here are Q4 sales by region...

You: Add year-over-year comparison
AI: [Adds YoY comparison]
    Here's the comparison...
```

#### Business Mode

Enable "Business Mode" for:
- Natural language summaries
- Confidence scores
- Data provenance
- Automatic insights

```
Question: Show product performance
Result: "Found 156 products. Top performer is 'Mountain Bike' 
         with $45K revenue. Average profit margin is 34%. 
         Three products showing declining trend..."
Confidence: High (0.92)
Source: Production.Product, Sales.SalesOrderDetail
```

---

### API Examples

#### Python Client

```python
import requests
import json

class AskLyticsClient:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.session_id = None
    
    def ask(self, question):
        """Ask a question and get results."""
        url = f"{self.base_url}/api/gemini_ask/stream"
        headers = {
            "Content-Type": "application/json",
            "X-Role": "user"
        }
        data = {"question": question}
        
        response = requests.post(url, headers=headers, json=data, stream=True)
        
        results = {}
        for line in response.iter_lines():
            if line.startswith(b'event: '):
                event_type = line[7:].decode()
            elif line.startswith(b'data: '):
                event_data = json.loads(line[6:])
                results[event_type] = event_data
        
        return results
    
    def get_data_only(self, question):
        """Get just the data results."""
        results = self.ask(question)
        if 'result' in results:
            return results['result']['data']
        return None

# Usage
client = AskLyticsClient()

# Simple query
data = client.get_data_only("Show top 5 products by sales")
for row in data:
    print(f"{row['ProductName']}: ${row['Sales']:,.2f}")

# Get full response
results = client.ask("Show sales by region")
print(f"SQL: {results['sql_complete']['query']}")
print(f"Rows: {len(results['result']['data'])}")
```

---

#### JavaScript/TypeScript

```typescript
class AskLyticsClient {
    private baseUrl: string;
    
    constructor(baseUrl = 'http://localhost:5000') {
        this.baseUrl = baseUrl;
    }
    
    async ask(question: string): Promise<any> {
        const response = await fetch(`${this.baseUrl}/api/gemini_ask/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Role': 'user'
            },
            body: JSON.stringify({ question })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        const results = {};
        
        let eventType = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    eventType = line.substring(7);
                } else if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.substring(6));
                    results[eventType] = data;
                }
            }
        }
        
        return results;
    }
}

// Usage
const client = new AskLyticsClient();
const results = await client.ask('Show sales by region');
console.log('Data:', results.result.data);
```

---

#### cURL Examples

```bash
# Basic query
curl -X POST http://localhost:5000/api/gemini_ask/stream \
  -H "Content-Type: application/json" \
  -H "X-Role: user" \
  -d '{"question": "Show top 10 customers"}'

# With PII unmasking
curl -X POST http://localhost:5000/api/gemini_ask/stream \
  -H "Content-Type: application/json" \
  -H "X-Role: pii_viewer" \
  -d '{
    "question": "Show customer contact details",
    "unmask": true,
    "pii_reason": "Customer outreach campaign - approved by marketing director"
  }'

# Force specific SQL
curl -X POST http://localhost:5000/api/gemini_ask/stream \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Custom query",
    "force_sql": "SELECT * FROM Sales.Customer WHERE CustomerID < 100"
  }'
```

---

### PowerShell Examples

```powershell
# Simple query
$body = @{
    question = "Show sales by region"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:5000/api/gemini_ask/stream" `
    -Method Post `
    -ContentType "application/json" `
    -Headers @{"X-Role" = "user"} `
    -Body $body

$response.result.data | Format-Table

# Export to CSV
$response.result.data | Export-Csv -Path "sales_by_region.csv" -NoTypeInformation
```

---

## Common Workflows

### Workflow 1: Sales Analysis

```
Step 1: Overview
Q: "Show me total sales for this year"

Step 2: Breakdown
Q: "Break that down by quarter"

Step 3: Comparison
Q: "Compare to last year"

Step 4: Top Performers
Q: "Show the top performing products"

Step 5: Export
Click "Export CSV" button
```

---

### Workflow 2: Customer Insights

```
Step 1: Segmentation
Q: "Show customers by lifetime value segments"

Step 2: Analysis
Q: "What's the average order value for each segment?"

Step 3: Trends
Q: "Show monthly new customer acquisition"

Step 4: Retention
Q: "Calculate customer retention rate by cohort"
```

---

### Workflow 3: Inventory Management

```
Step 1: Current State
Q: "Show current inventory levels by warehouse"

Step 2: Low Stock
Q: "Which products are below reorder point?"

Step 3: Fast Movers
Q: "What are the top 20 fastest moving products?"

Step 4: Forecast
Q: "Show sales velocity trend for each product"
```

---

### Workflow 4: Financial Reporting

```
Step 1: Revenue
Q: "Show monthly revenue for the last 12 months"

Step 2: Profit Margins
Q: "Calculate profit margin by product category"

Step 3: Cost Analysis
Q: "Show cost breakdown by department"

Step 4: Variance
Q: "Compare actual vs budget for Q4"
```

---

## Best Practices

### 1. Be Specific

❌ **Vague:**
```
Show me some data
```

✅ **Specific:**
```
Show the top 10 customers by revenue in 2025
```

---

### 2. Use Context

❌ **No Context:**
```
Show sales
```

✅ **With Context:**
```
Show daily sales for the last 30 days, grouped by product category
```

---

### 3. Iterate

Start broad, then refine:

```
1. "Show all orders"
2. "Filter to just this month"
3. "Sort by order value"
4. "Show only orders over $1000"
```

---

### 4. Provide Feedback

After each query:
- ✅ **Correct** if results match your expectations
- ❌ **Incorrect** if results are wrong
- Add comments to help the system learn

```
Feedback: Correct ✓
Comment: "Perfect! Exactly what I needed"
```

---

### 5. Use Business Mode

Enable for:
- Executive dashboards
- Client-facing reports
- Auditable analysis
- Compliance requirements

Provides:
- Confidence scores
- Data provenance
- Natural language summaries
- Audit trail

---

### 6. Leverage Sessions

Keep related queries in the same session:

```
Session 1: Sales Analysis
- Q1 sales by region
- Top performers
- YoY comparison

Session 2: Inventory Review
- Stock levels
- Reorder recommendations
- Warehouse capacity
```

---

### 7. Export and Share

**CSV Export:**
- Click "Export CSV" button
- Opens in Excel/Google Sheets
- Preserves formatting

**Share SQL:**
- Copy generated SQL
- Run in SSMS/Azure Data Studio
- Add to stored procedures

---

## Next Steps

### Beginner → Intermediate

1. **Learn SQL Basics**
   - Understand what AskLytics generates
   - Modify SQL for custom needs
   - Create reusable queries

2. **Explore Advanced Features**
   - Business Mode
   - Confidence scoring
   - Feedback loop
   - Regression testing

3. **Integrate with Tools**
   - Power BI (via API)
   - Excel (via CSV export)
   - Python notebooks
   - Custom dashboards

---

### Intermediate → Advanced

1. **API Integration**
   - Build custom clients
   - Automate reporting
   - Create workflows
   - Embed in applications

2. **Governance Setup**
   - Configure PII masking
   - Set up role-based access
   - Review audit logs
   - Compliance reporting

3. **Performance Tuning**
   - Optimize connection pool
   - Configure caching
   - Index selection
   - Query optimization

---

### Advanced → Expert

1. **Custom Training**
   - Add verified examples
   - Build regression suites
   - Fine-tune retrieval
   - Optimize embeddings

2. **Production Deployment**
   - Docker containers
   - Load balancing
   - High availability
   - Monitoring & alerts

3. **Extension Development**
   - Custom validators
   - Additional LLM providers
   - New data sources
   - Plugin architecture

---

## Troubleshooting Quick Reference

### Can't Connect to Database

```bash
# Test connection
sqlcmd -S localhost -U sa -P YourPassword123 -Q "SELECT 1"

# Check ODBC drivers
odbcinst -j

# Verify .env settings
cat .env | grep DB_
```

---

### SQL Generation Errors

**Low confidence scores:**
- Add more training examples
- Improve table/column selection
- Check schema metadata

**Wrong tables used:**
- Review selected tables in settings
- Add descriptions to tables
- Provide example queries

**Syntax errors:**
- Check SQL dialect (T-SQL only)
- Review column names
- Verify foreign keys

---

### Performance Issues

**Slow queries:**
- Check connection pool size
- Review query timeout settings
- Optimize database indexes

**High memory usage:**
- Use smaller model quantization (Q4 instead of Q8)
- Reduce context window size
- Enable query caching

---

## Getting Help

### Documentation

- [API Reference](./API_REFERENCE.md)
- [Configuration Guide](./CONFIGURATION.md)
- [Learning Engine](./LEARNING_ENGINE.md)
- [Governance Module](./GOVERNANCE_MODULE.md)

### Community

- GitHub Issues: https://github.com/your-org/asklytics/issues
- Discussions: https://github.com/your-org/asklytics/discussions
- Email: support@asklytics.com

### Support

- Documentation: Full guides and examples
- Video Tutorials: Step-by-step walkthroughs
- Sample Projects: Pre-configured examples
- Professional Support: Enterprise support available

---

## What You've Learned

✅ Installation and setup
✅ Database configuration
✅ Running your first query
✅ Using the API
✅ Common workflows
✅ Best practices
✅ Troubleshooting

## Where to Go Next

1. **Explore Examples:** Try the workflows above
2. **Read API Docs:** Learn advanced features
3. **Join Community:** Share your experience
4. **Build Something:** Create your first integration

---

**Welcome to AskLytics! 🚀**

Start asking questions and let AI handle the SQL complexity.

*Last Updated: October 30, 2025*


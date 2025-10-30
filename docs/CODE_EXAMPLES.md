# Code Examples & Integration Guide

Practical code examples for integrating AskLytics into your applications.

## Table of Contents

- [Python Examples](#python-examples)
- [JavaScript Examples](#javascript-examples)
- [REST API Examples](#rest-api-examples)
- [Integration Patterns](#integration-patterns)
- [Real-World Use Cases](#real-world-use-cases)
- [Testing Examples](#testing-examples)

---

## Python Examples

### Basic Client Library

```python
"""
AskLytics Python Client
Simple wrapper for the AskLytics API
"""

import requests
import json
import uuid
from typing import Dict, List, Optional, Generator
from dataclasses import dataclass

@dataclass
class QueryResult:
    """Represents a query result from AskLytics."""
    question: str
    sql: str
    columns: List[str]
    data: List[Dict]
    confidence: Optional[float] = None
    confidence_label: Optional[str] = None
    explanation: Optional[str] = None
    summary: Optional[str] = None

class AskLyticsClient:
    """Client for AskLytics API."""
    
    def __init__(self, base_url: str = "http://localhost:5000", role: str = "user"):
        """
        Initialize AskLytics client.
        
        Args:
            base_url: AskLytics server URL
            role: User role (user, admin, auditor, pii_viewer)
        """
        self.base_url = base_url.rstrip('/')
        self.role = role
        self.session_id = str(uuid.uuid4())
    
    def ask(self, question: str, unmask: bool = False, 
            pii_reason: Optional[str] = None) -> QueryResult:
        """
        Ask a question and get results.
        
        Args:
            question: Natural language question
            unmask: Whether to unmask PII (requires pii_viewer role)
            pii_reason: Justification for PII access (required if unmask=True)
        
        Returns:
            QueryResult with data and metadata
        
        Raises:
            ValueError: If unmask=True but pii_reason is not provided
            requests.HTTPError: If API request fails
        """
        if unmask and not pii_reason:
            raise ValueError("pii_reason is required when unmask=True")
        
        url = f"{self.base_url}/api/gemini_ask/stream"
        headers = {
            "Content-Type": "application/json",
            "X-Role": self.role,
            "X-Session-ID": self.session_id
        }
        body = {"question": question}
        
        if unmask:
            body["unmask"] = True
            body["pii_reason"] = pii_reason
        
        response = requests.post(url, headers=headers, json=body, stream=True)
        response.raise_for_status()
        
        # Parse SSE stream
        events = {}
        current_event = None
        
        for line in response.iter_lines():
            if line.startswith(b'event: '):
                current_event = line[7:].decode()
            elif line.startswith(b'data: '):
                data = json.loads(line[6:])
                events[current_event] = data
        
        # Build result
        return QueryResult(
            question=question,
            sql=events.get('sql_complete', {}).get('query', ''),
            columns=events.get('result', {}).get('columns', []),
            data=events.get('result', {}).get('data', []),
            confidence=events.get('confidence', {}).get('score'),
            confidence_label=events.get('confidence', {}).get('label'),
            explanation=events.get('explanation', {}).get('text'),
            summary=events.get('summary', {}).get('summary')
        )
    
    def stream_ask(self, question: str) -> Generator[Dict, None, None]:
        """
        Ask a question and stream events as they arrive.
        
        Args:
            question: Natural language question
        
        Yields:
            Event dictionaries as they arrive
        """
        url = f"{self.base_url}/api/gemini_ask/stream"
        headers = {
            "Content-Type": "application/json",
            "X-Role": self.role,
            "X-Session-ID": self.session_id
        }
        body = {"question": question}
        
        response = requests.post(url, headers=headers, json=body, stream=True)
        response.raise_for_status()
        
        current_event = None
        for line in response.iter_lines():
            if line.startswith(b'event: '):
                current_event = line[7:].decode()
            elif line.startswith(b'data: '):
                data = json.loads(line[6:])
                yield {"event": current_event, "data": data}
    
    def submit_feedback(self, xp_id: int, verdict: str, 
                       comment: Optional[str] = None,
                       confidence: Optional[float] = None) -> int:
        """
        Submit feedback on a query result.
        
        Args:
            xp_id: Experience ID from query
            verdict: "correct" or "incorrect"
            comment: Optional comment
            confidence: Optional confidence score (0-1)
        
        Returns:
            Feedback ID
        """
        url = f"{self.base_url}/api/feedback"
        headers = {
            "Content-Type": "application/json",
            "X-Role": self.role
        }
        body = {
            "xp_id": xp_id,
            "verdict": verdict
        }
        
        if comment:
            body["comment"] = comment
        if confidence is not None:
            body["confidence"] = confidence
        
        response = requests.post(url, headers=headers, json=body)
        response.raise_for_status()
        
        return response.json()["feedback_id"]
    
    def get_confidence_trend(self, weeks: int = 8) -> List[Dict]:
        """Get confidence trend over time."""
        url = f"{self.base_url}/api/metrics/confidence_trend"
        params = {"weeks": weeks}
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()["trend"]


# Usage Examples

if __name__ == "__main__":
    # Initialize client
    client = AskLyticsClient(base_url="http://localhost:5000")
    
    # Example 1: Simple query
    print("Example 1: Simple Query")
    result = client.ask("Show top 10 customers by revenue")
    print(f"SQL: {result.sql}")
    print(f"Found {len(result.data)} rows")
    for row in result.data[:3]:
        print(row)
    
    # Example 2: Stream query
    print("\nExample 2: Streaming Query")
    for event in client.stream_ask("Show sales by region"):
        print(f"{event['event']}: {event['data']}")
    
    # Example 3: Query with PII
    print("\nExample 3: PII Access")
    pii_client = AskLyticsClient(role="pii_viewer")
    result = pii_client.ask(
        "Show customer email addresses",
        unmask=True,
        pii_reason="Customer outreach campaign - approved by CMO"
    )
    print(f"Retrieved {len(result.data)} customer records")
    
    # Example 4: Submit feedback
    print("\nExample 4: Feedback")
    feedback_id = client.submit_feedback(
        xp_id=123,
        verdict="correct",
        comment="Perfect results!",
        confidence=0.95
    )
    print(f"Feedback submitted: {feedback_id}")
    
    # Example 5: Get metrics
    print("\nExample 5: Metrics")
    trend = client.get_confidence_trend(weeks=4)
    for week in trend:
        print(f"{week['week_start']}: {week['avg_confidence']:.2f}")
```

---

### Pandas Integration

```python
"""
AskLytics + Pandas Integration
Query data and analyze with pandas
"""

import pandas as pd
from asklytics_client import AskLyticsClient

def ask_to_dataframe(client: AskLyticsClient, question: str) -> pd.DataFrame:
    """
    Query AskLytics and return results as pandas DataFrame.
    
    Args:
        client: AskLyticsClient instance
        question: Natural language question
    
    Returns:
        DataFrame with query results
    """
    result = client.ask(question)
    return pd.DataFrame(result.data)


# Example usage
client = AskLyticsClient()

# Get sales data
df = ask_to_dataframe(client, "Show daily sales for the last 30 days")

# Analyze with pandas
print(df.describe())
print(df['Sales'].sum())
print(df.groupby('Region')['Sales'].mean())

# Visualize
import matplotlib.pyplot as plt

df['Date'] = pd.to_datetime(df['Date'])
df.set_index('Date')['Sales'].plot()
plt.title("Sales Trend")
plt.show()

# Export
df.to_csv('sales_data.csv', index=False)
df.to_excel('sales_data.xlsx', index=False)
```

---

### Async Client

```python
"""
Async AskLytics Client
For high-performance applications
"""

import asyncio
import aiohttp
import json
from typing import Dict, AsyncGenerator

class AsyncAskLyticsClient:
    """Async client for AskLytics API."""
    
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
    
    async def ask(self, question: str) -> Dict:
        """Async query."""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/gemini_ask/stream"
            headers = {"Content-Type": "application/json"}
            body = {"question": question}
            
            async with session.post(url, headers=headers, json=body) as response:
                events = {}
                current_event = None
                
                async for line in response.content:
                    line = line.decode()
                    if line.startswith('event: '):
                        current_event = line[7:].strip()
                    elif line.startswith('data: '):
                        data = json.loads(line[6:])
                        events[current_event] = data
                
                return events
    
    async def ask_many(self, questions: list) -> list:
        """Query multiple questions concurrently."""
        tasks = [self.ask(q) for q in questions]
        return await asyncio.gather(*tasks)


# Usage
async def main():
    client = AsyncAskLyticsClient()
    
    # Single query
    result = await client.ask("Show sales by region")
    print(result['result']['data'])
    
    # Multiple concurrent queries
    questions = [
        "Show top customers",
        "Show product inventory",
        "Show monthly revenue"
    ]
    results = await client.ask_many(questions)
    for q, r in zip(questions, results):
        print(f"{q}: {len(r['result']['data'])} rows")

asyncio.run(main())
```

---

## JavaScript Examples

### Browser Client

```javascript
/**
 * AskLytics JavaScript Client
 * For browser-based applications
 */

class AskLyticsClient {
    constructor(baseUrl = 'http://localhost:5000') {
        this.baseUrl = baseUrl;
        this.sessionId = this.generateUUID();
    }
    
    generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }
    
    /**
     * Ask a question and get complete results
     */
    async ask(question, options = {}) {
        const url = `${this.baseUrl}/api/gemini_ask/stream`;
        const headers = {
            'Content-Type': 'application/json',
            'X-Role': options.role || 'user',
            'X-Session-ID': this.sessionId
        };
        
        const body = {question};
        if (options.unmask) {
            body.unmask = true;
            body.pii_reason = options.piiReason;
        }
        
        const response = await fetch(url, {
            method: 'POST',
            headers,
            body: JSON.stringify(body)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        // Parse SSE stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        const events = {};
        
        let currentEvent = null;
        let buffer = '';
        
        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, {stream: true});
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer
            
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    currentEvent = line.substring(7);
                } else if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.substring(6));
                    events[currentEvent] = data;
                }
            }
        }
        
        return {
            question,
            sql: events.sql_complete?.query || '',
            columns: events.result?.columns || [],
            data: events.result?.data || [],
            confidence: events.confidence?.score,
            confidenceLabel: events.confidence?.label,
            explanation: events.explanation?.text,
            summary: events.summary?.summary
        };
    }
    
    /**
     * Stream query events
     */
    streamAsk(question, onEvent, options = {}) {
        const url = `${this.baseUrl}/api/gemini_ask/stream`;
        const headers = {
            'Content-Type': 'application/json',
            'X-Role': options.role || 'user',
            'X-Session-ID': this.sessionId
        };
        
        const body = {question};
        
        fetch(url, {
            method: 'POST',
            headers,
            body: JSON.stringify(body)
        }).then(response => {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            let currentEvent = null;
            let buffer = '';
            
            const read = () => {
                reader.read().then(({done, value}) => {
                    if (done) {
                        onEvent('complete', {});
                        return;
                    }
                    
                    buffer += decoder.decode(value, {stream: true});
                    const lines = buffer.split('\n');
                    buffer = lines.pop();
                    
                    for (const line of lines) {
                        if (line.startsWith('event: ')) {
                            currentEvent = line.substring(7);
                        } else if (line.startsWith('data: ')) {
                            const data = JSON.parse(line.substring(6));
                            onEvent(currentEvent, data);
                        }
                    }
                    
                    read();
                });
            };
            
            read();
        });
    }
    
    /**
     * Submit feedback
     */
    async submitFeedback(xpId, verdict, comment = null, confidence = null) {
        const url = `${this.baseUrl}/api/feedback`;
        const headers = {
            'Content-Type': 'application/json'
        };
        
        const body = {
            xp_id: xpId,
            verdict
        };
        
        if (comment) body.comment = comment;
        if (confidence !== null) body.confidence = confidence;
        
        const response = await fetch(url, {
            method: 'POST',
            headers,
            body: JSON.stringify(body)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const result = await response.json();
        return result.feedback_id;
    }
}

// Usage Examples

// Example 1: Basic query
const client = new AskLyticsClient();
const result = await client.ask("Show top 10 customers");
console.log('Results:', result.data);

// Example 2: Streaming query
client.streamAsk("Show sales by region", (event, data) => {
    switch(event) {
        case 'sql_complete':
            console.log('SQL:', data.query);
            break;
        case 'result':
            displayResults(data.columns, data.data);
            break;
        case 'explanation':
            showExplanation(data.text);
            break;
        case 'complete':
            console.log('Query complete');
            break;
    }
});

// Example 3: Display in table
function displayResults(columns, data) {
    const table = document.createElement('table');
    
    // Header
    const thead = table.createTHead();
    const headerRow = thead.insertRow();
    columns.forEach(col => {
        const th = document.createElement('th');
        th.textContent = col;
        headerRow.appendChild(th);
    });
    
    // Body
    const tbody = table.createTBody();
    data.forEach(row => {
        const tr = tbody.insertRow();
        columns.forEach(col => {
            const td = tr.insertCell();
            td.textContent = row[col];
        });
    });
    
    document.body.appendChild(table);
}

// Example 4: Submit feedback
document.getElementById('thumbs-up').addEventListener('click', async () => {
    await client.submitFeedback(currentXpId, 'correct', null, 0.95);
    alert('Thank you for your feedback!');
});
```

---

### React Component

```jsx
/**
 * AskLytics React Component
 */

import React, { useState } from 'react';
import { AskLyticsClient } from './asklytics-client';

function AskLyticsQuery() {
    const [question, setQuestion] = useState('');
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    
    const client = new AskLyticsClient();
    
    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        
        try {
            const result = await client.ask(question);
            setResult(result);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };
    
    return (
        <div className="asklytics-query">
            <form onSubmit={handleSubmit}>
                <input
                    type="text"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="Ask a question..."
                    disabled={loading}
                />
                <button type="submit" disabled={loading}>
                    {loading ? 'Querying...' : 'Ask'}
                </button>
            </form>
            
            {error && (
                <div className="error">
                    Error: {error}
                </div>
            )}
            
            {result && (
                <div className="results">
                    <div className="sql">
                        <strong>SQL:</strong>
                        <pre>{result.sql}</pre>
                    </div>
                    
                    <div className="confidence">
                        <strong>Confidence:</strong> {result.confidenceLabel} ({result.confidence?.toFixed(2)})
                    </div>
                    
                    {result.explanation && (
                        <div className="explanation">
                            <strong>Explanation:</strong>
                            <p>{result.explanation}</p>
                        </div>
                    )}
                    
                    <table>
                        <thead>
                            <tr>
                                {result.columns.map(col => (
                                    <th key={col}>{col}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {result.data.map((row, i) => (
                                <tr key={i}>
                                    {result.columns.map(col => (
                                        <td key={col}>{row[col]}</td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

export default AskLyticsQuery;
```

---

## REST API Examples

### PowerShell

```powershell
# AskLytics PowerShell Module

function Invoke-AskLytics {
    <#
    .SYNOPSIS
        Query AskLytics from PowerShell
    .DESCRIPTION
        Send natural language questions to AskLytics and get SQL results
    .PARAMETER Question
        Natural language question
    .PARAMETER BaseUrl
        AskLytics server URL
    .EXAMPLE
        Invoke-AskLytics -Question "Show top 10 customers"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$Question,
        
        [Parameter()]
        [string]$BaseUrl = "http://localhost:5000"
    )
    
    $uri = "$BaseUrl/api/gemini_ask/stream"
    $headers = @{
        "Content-Type" = "application/json"
        "X-Role" = "user"
    }
    $body = @{
        question = $Question
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $body
        return $response
    }
    catch {
        Write-Error "Failed to query AskLytics: $_"
    }
}

# Usage
$result = Invoke-AskLytics -Question "Show sales by region"
$result.result.data | Format-Table
$result.result.data | Export-Csv -Path "sales.csv" -NoTypeInformation
```

---

### Bash/cURL

```bash
#!/bin/bash
# AskLytics Bash Client

ASKLYTICS_URL="http://localhost:5000"

ask_lytics() {
    local question="$1"
    local role="${2:-user}"
    
    curl -s -X POST "${ASKLYTICS_URL}/api/gemini_ask/stream" \
        -H "Content-Type: application/json" \
        -H "X-Role: ${role}" \
        -d "{\"question\": \"${question}\"}"
}

# Usage
ask_lytics "Show top 10 customers"

# With jq for pretty output
ask_lytics "Show sales by region" | jq '.result.data'

# Save to file
ask_lytics "Show product inventory" > inventory_$(date +%Y%m%d).json
```

---

## Integration Patterns

### Pattern 1: Scheduled Reports

```python
"""
Generate and email daily reports
"""

from asklytics_client import AskLyticsClient
import pandas as pd
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import smtplib

def generate_daily_report():
    client = AskLyticsClient()
    
    # Query data
    sales_result = client.ask("Show yesterday's sales by region")
    top_customers = client.ask("Show top 20 customers from yesterday")
    
    # Create DataFrames
    df_sales = pd.DataFrame(sales_result.data)
    df_customers = pd.DataFrame(top_customers.data)
    
    # Generate Excel report
    with pd.ExcelWriter('daily_report.xlsx') as writer:
        df_sales.to_excel(writer, sheet_name='Sales by Region', index=False)
        df_customers.to_excel(writer, sheet_name='Top Customers', index=False)
    
    # Email report
    send_email(
        to='manager@company.com',
        subject='Daily Sales Report',
        body='Please find attached the daily sales report.',
        attachment='daily_report.xlsx'
    )

def send_email(to, subject, body, attachment):
    msg = MIMEMultipart()
    msg['From'] = 'reports@company.com'
    msg['To'] = to
    msg['Subject'] = subject
    
    msg.attach(MIMEText(body, 'plain'))
    
    with open(attachment, 'rb') as f:
        attach = MIMEApplication(f.read(), _subtype="xlsx")
        attach.add_header('Content-Disposition', 'attachment', filename=attachment)
        msg.attach(attach)
    
    server = smtplib.SMTP('smtp.company.com', 587)
    server.starttls()
    server.login('reports@company.com', 'password')
    server.send_message(msg)
    server.quit()

# Schedule with cron or Task Scheduler
if __name__ == "__main__":
    generate_daily_report()
```

---

### Pattern 2: Slack Bot

```python
"""
AskLytics Slack Bot
Ask questions via Slack
"""

from slack_bolt import App
from asklytics_client import AskLyticsClient
import pandas as pd

app = App(token="xoxb-your-token")
asklytics = AskLyticsClient()

@app.message("ask:")
def handle_ask(message, say):
    question = message['text'].replace('ask:', '').strip()
    
    try:
        result = asklytics.ask(question)
        
        # Format response
        df = pd.DataFrame(result.data)
        table = df.to_markdown(index=False)
        
        say(f"*Question:* {question}\n\n*Results:*\n```\n{table}\n```\n\n*Confidence:* {result.confidence_label}")
    except Exception as e:
        say(f"Error: {e}")

if __name__ == "__main__":
    app.start(port=3000)
```

---

### Pattern 3: API Gateway

```python
"""
Wrap AskLytics in a custom API with caching
"""

from flask import Flask, request, jsonify
from functools import lru_cache
from asklytics_client import AskLyticsClient
import hashlib

app = Flask(__name__)
client = AskLyticsClient()

@lru_cache(maxsize=100)
def cached_query(question_hash):
    question = cache_keys[question_hash]
    return client.ask(question)

cache_keys = {}

@app.route('/query', methods=['POST'])
def query():
    question = request.json['question']
    
    # Create cache key
    question_hash = hashlib.md5(question.encode()).hexdigest()
    cache_keys[question_hash] = question
    
    # Query (cached)
    result = cached_query(question_hash)
    
    return jsonify({
        'question': question,
        'data': result.data,
        'cached': question_hash in cached_query.cache_info().currsize
    })

if __name__ == '__main__':
    app.run(port=8080)
```

---

## Real-World Use Cases

### Use Case 1: Executive Dashboard

```python
"""
Real-time executive dashboard with Flask + AskLytics
"""

from flask import Flask, render_template_string
from asklytics_client import AskLyticsClient
import json

app = Flask(__name__)
client = AskLyticsClient()

DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Executive Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <h1>Executive Dashboard</h1>
    <div id="metrics">
        <div class="metric">
            <h3>Today's Revenue</h3>
            <p>${{ revenue|number_format }}</p>
        </div>
        <div class="metric">
            <h3>New Customers</h3>
            <p>{{ new_customers }}</p>
        </div>
        <div class="metric">
            <h3>Orders</h3>
            <p>{{ order_count }}</p>
        </div>
    </div>
    
    <canvas id="revenueChart"></canvas>
    
    <script>
        const data = {{ chart_data|tojson }};
        new Chart(document.getElementById('revenueChart'), {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Revenue',
                    data: data.values
                }]
            }
        });
    </script>
</body>
</html>
'''

@app.route('/')
def dashboard():
    # Query metrics
    revenue_result = client.ask("Show today's total revenue")
    customers_result = client.ask("Count new customers today")
    orders_result = client.ask("Count orders today")
    trend_result = client.ask("Show daily revenue for last 30 days")
    
    # Extract values
    revenue = revenue_result.data[0]['Revenue']
    new_customers = customers_result.data[0]['Count']
    order_count = orders_result.data[0]['Count']
    
    # Chart data
    chart_data = {
        'labels': [row['Date'] for row in trend_result.data],
        'values': [row['Revenue'] for row in trend_result.data]
    }
    
    return render_template_string(
        DASHBOARD_TEMPLATE,
        revenue=revenue,
        new_customers=new_customers,
        order_count=order_count,
        chart_data=chart_data
    )

if __name__ == '__main__':
    app.run()
```

---

### Use Case 2: Data Quality Monitoring

```python
"""
Monitor data quality with AskLytics
"""

from asklytics_client import AskLyticsClient
import schedule
import time

client = AskLyticsClient()

def check_data_quality():
    checks = {
        "Null emails": "SELECT COUNT(*) FROM Customers WHERE Email IS NULL",
        "Duplicate orders": "SELECT COUNT(*) FROM (SELECT OrderID, COUNT(*) as cnt FROM Orders GROUP BY OrderID HAVING COUNT(*) > 1) x",
        "Negative prices": "SELECT COUNT(*) FROM Products WHERE Price < 0",
        "Future dates": "SELECT COUNT(*) FROM Orders WHERE OrderDate > GETDATE()"
    }
    
    alerts = []
    for check_name, sql in checks.items():
        result = client.ask(sql)
        count = result.data[0]['Count']
        if count > 0:
            alerts.append(f"{check_name}: {count} issues found")
    
    if alerts:
        send_alert("\n".join(alerts))

def send_alert(message):
    # Send to Slack, email, etc.
    print(f"ALERT: {message}")

# Run every hour
schedule.every().hour.do(check_data_quality)

while True:
    schedule.run_pending()
    time.sleep(60)
```

---

## Testing Examples

### Unit Tests

```python
"""
Unit tests for AskLytics integration
"""

import unittest
from unittest.mock import Mock, patch
from asklytics_client import AskLyticsClient

class TestAskLyticsClient(unittest.TestCase):
    def setUp(self):
        self.client = AskLyticsClient(base_url="http://test:5000")
    
    @patch('requests.post')
    def test_ask(self, mock_post):
        # Mock response
        mock_response = Mock()
        mock_response.iter_lines.return_value = [
            b'event: sql_complete',
            b'data: {"query": "SELECT * FROM test"}',
            b'event: result',
            b'data: {"columns": ["id", "name"], "data": [{"id": 1, "name": "test"}]}'
        ]
        mock_post.return_value = mock_response
        
        # Test
        result = self.client.ask("test question")
        
        self.assertEqual(result.sql, "SELECT * FROM test")
        self.assertEqual(len(result.data), 1)
        self.assertEqual(result.data[0]['name'], 'test')
    
    def test_unmask_requires_reason(self):
        with self.assertRaises(ValueError):
            self.client.ask("test", unmask=True)

if __name__ == '__main__':
    unittest.main()
```

---

### Integration Tests

```python
"""
Integration tests with live AskLytics instance
"""

import pytest
from asklytics_client import AskLyticsClient

@pytest.fixture
def client():
    return AskLyticsClient(base_url="http://localhost:5000")

def test_simple_query(client):
    result = client.ask("Show top 5 customers")
    assert len(result.data) <= 5
    assert result.confidence is not None

def test_feedback_workflow(client):
    # Query
    result = client.ask("Show sales by region")
    
    # Submit feedback
    feedback_id = client.submit_feedback(
        xp_id=result.xp_id,
        verdict="correct",
        confidence=0.9
    )
    
    assert feedback_id > 0

@pytest.mark.requires_pii_access
def test_pii_access(client):
    pii_client = AskLyticsClient(role="pii_viewer")
    result = pii_client.ask(
        "Show customer emails",
        unmask=True,
        pii_reason="Testing PII access"
    )
    
    assert len(result.data) > 0
    # Verify data is unmasked
    assert '@' in result.data[0].get('Email', '')
```

---

*Last Updated: October 30, 2025*
*Code Examples Version: 1.0.0*



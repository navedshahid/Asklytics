#!/usr/bin/env python3
"""Seed the experience store with sample data for testing."""

import os
import sys
import sqlite3
from datetime import datetime, timedelta

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def seed_experiences():
    """Add sample experiences to the learning store."""
    db_path = "learning_store.db"
    
    # Sample experiences
    sample_experiences = [
        {
            "user_prompt": "show me all customers",
            "generated_sql": "SELECT * FROM customers",
            "validated_sql": "SELECT * FROM customers",
            "schema_context": "customers table with id, name, email columns",
            "result_signature": "3 columns, 150 rows",
            "score": 0.95,
            "success": True,
            "feedback": "correct",
            "provider": "gemini",
            "exec_ms": 45.2,
            "tables_used": "customers",
            "joins": "",
            "validation_signals": '{"syntax_ok": true, "has_select": true, "no_destructive": true}',
            "confidence_score": 0.95,
            "confidence_label": "High"
        },
        {
            "user_prompt": "count total orders",
            "generated_sql": "SELECT COUNT(*) FROM orders",
            "validated_sql": "SELECT COUNT(*) FROM orders",
            "schema_context": "orders table with id, customer_id, order_date columns",
            "result_signature": "1 column, 1 row",
            "score": 0.98,
            "success": True,
            "feedback": "correct",
            "provider": "gemini",
            "exec_ms": 23.1,
            "tables_used": "orders",
            "joins": "",
            "validation_signals": '{"syntax_ok": true, "has_select": true, "has_aggregate": true}',
            "confidence_score": 0.98,
            "confidence_label": "High"
        },
        {
            "user_prompt": "top 10 products by sales",
            "generated_sql": "SELECT TOP 10 product_name, SUM(quantity) as total_sales FROM order_items oi JOIN products p ON oi.product_id = p.id GROUP BY product_name ORDER BY total_sales DESC",
            "validated_sql": "SELECT TOP 10 product_name, SUM(quantity) as total_sales FROM order_items oi JOIN products p ON oi.product_id = p.id GROUP BY product_name ORDER BY total_sales DESC",
            "schema_context": "products and order_items tables",
            "result_signature": "2 columns, 10 rows",
            "score": 0.92,
            "success": True,
            "feedback": "correct",
            "provider": "gemini",
            "exec_ms": 156.7,
            "tables_used": "products,order_items",
            "joins": "order_items.product_id = products.id",
            "validation_signals": '{"syntax_ok": true, "has_select": true, "has_join": true, "has_group_by": true}',
            "confidence_score": 0.92,
            "confidence_label": "High"
        },
        {
            "user_prompt": "average price by category",
            "generated_sql": "SELECT category, AVG(price) as avg_price FROM products GROUP BY category",
            "validated_sql": "SELECT category, AVG(price) as avg_price FROM products GROUP BY category",
            "schema_context": "products table with category and price columns",
            "result_signature": "2 columns, 5 rows",
            "score": 0.89,
            "success": True,
            "feedback": "correct",
            "provider": "gemini",
            "exec_ms": 67.3,
            "tables_used": "products",
            "joins": "",
            "validation_signals": '{"syntax_ok": true, "has_select": true, "has_aggregate": true, "has_group_by": true}',
            "confidence_score": 0.89,
            "confidence_label": "High"
        },
        {
            "user_prompt": "customers with orders in last 30 days",
            "generated_sql": "SELECT DISTINCT c.name, c.email FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.order_date >= DATEADD(day, -30, GETDATE())",
            "validated_sql": "SELECT DISTINCT c.name, c.email FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.order_date >= DATEADD(day, -30, GETDATE())",
            "schema_context": "customers and orders tables with date filtering",
            "result_signature": "2 columns, 25 rows",
            "score": 0.87,
            "success": True,
            "feedback": "correct",
            "provider": "gemini",
            "exec_ms": 89.4,
            "tables_used": "customers,orders",
            "joins": "customers.id = orders.customer_id",
            "validation_signals": '{"syntax_ok": true, "has_select": true, "has_join": true, "has_where": true}',
            "confidence_score": 0.87,
            "confidence_label": "High"
        }
    ]
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    try:
        # Ensure table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS xp (
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
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                exec_ms REAL,
                error_type TEXT,
                tables_used TEXT,
                joins TEXT,
                validation_signals TEXT DEFAULT '{}',
                confidence_score REAL DEFAULT 0.0,
                confidence_label TEXT DEFAULT 'Low'
            )
        """)
        
        # Insert sample experiences
        for i, exp in enumerate(sample_experiences):
            # Create timestamps spread over the last 30 days
            timestamp = datetime.now() - timedelta(days=30-i*7)
            conn.execute("""
                INSERT INTO xp (
                    user_prompt, generated_sql, validated_sql, schema_context,
                    result_signature, score, success, feedback, provider,
                    exec_ms, tables_used, joins, validation_signals,
                    confidence_score, confidence_label, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exp["user_prompt"], exp["generated_sql"], exp["validated_sql"],
                exp["schema_context"], exp["result_signature"], exp["score"],
                exp["success"], exp["feedback"], exp["provider"], exp["exec_ms"],
                exp["tables_used"], exp["joins"], exp["validation_signals"],
                exp["confidence_score"], exp["confidence_label"], timestamp
            ))
        
        conn.commit()
        print(f"Successfully added {len(sample_experiences)} sample experiences to the database.")
        
    except Exception as e:
        print(f"Error seeding experiences: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    seed_experiences()

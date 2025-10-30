"""
Seed SQLite database with retail sample data for semantic layer testing.

Creates tables and loads CSV data for customers, stores, products, orders, and order_items.
"""

import sqlite3
import csv
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path("data/retail.db")
SEED_DIR = Path("data/seed")


def create_tables(conn):
    """Create retail schema tables."""
    cursor = conn.cursor()
    
    # Customers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY,
            email TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            city TEXT,
            state TEXT,
            country TEXT,
            created_at TIMESTAMP
        )
    """)
    
    # Stores table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stores (
            store_id INTEGER PRIMARY KEY,
            store_name TEXT NOT NULL,
            city TEXT,
            state TEXT,
            region TEXT,
            manager_name TEXT,
            opened_date DATE
        )
    """)
    
    # Products table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY,
            sku TEXT NOT NULL UNIQUE,
            product_name TEXT NOT NULL,
            category TEXT,
            subcategory TEXT,
            list_price DECIMAL(10, 2),
            cost DECIMAL(10, 2),
            is_active INTEGER DEFAULT 1
        )
    """)
    
    # Orders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            store_id INTEGER,
            order_date TIMESTAMP,
            status TEXT,
            total_amount DECIMAL(10, 2),
            shipping_address TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
            FOREIGN KEY (store_id) REFERENCES stores(store_id)
        )
    """)
    
    # Order Items table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            order_item_id INTEGER PRIMARY KEY,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            unit_price DECIMAL(10, 2),
            discount DECIMAL(10, 2) DEFAULT 0,
            extended_price DECIMAL(10, 2),
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )
    """)
    
    # Create indices for better performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_store ON orders(store_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id)")
    
    conn.commit()
    print("✓ Tables created successfully")


def load_csv(conn, table_name, csv_file):
    """Load CSV file into table."""
    cursor = conn.cursor()
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames
        
        placeholders = ','.join(['?' for _ in columns])
        insert_sql = f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"
        
        rows_inserted = 0
        for row in reader:
            values = [row[col] for col in columns]
            cursor.execute(insert_sql, values)
            rows_inserted += 1
        
        conn.commit()
        print(f"✓ Loaded {rows_inserted} rows into {table_name}")


def main():
    """Main seeding function."""
    print("=" * 60)
    print("Seeding SQLite Retail Database")
    print("=" * 60)
    
    # Create database directory if needed
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if seed files exist
    if not SEED_DIR.exists():
        print(f"❌ Seed directory not found: {SEED_DIR}")
        print("Please ensure CSV files are in data/seed/")
        sys.exit(1)
    
    # Connect to database
    conn = sqlite3.connect(str(DB_PATH))
    
    try:
        # Create tables
        create_tables(conn)
        
        # Load data in order (respecting foreign keys)
        tables_order = [
            ('customers', 'customers.csv'),
            ('stores', 'stores.csv'),
            ('products', 'products.csv'),
            ('orders', 'orders.csv'),
            ('order_items', 'order_items.csv')
        ]
        
        for table_name, csv_filename in tables_order:
            csv_file = SEED_DIR / csv_filename
            if not csv_file.exists():
                print(f"⚠️  CSV file not found: {csv_file}")
                continue
            
            load_csv(conn, table_name, csv_file)
        
        # Verify data
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM customers")
        customer_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orders")
        order_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM order_items")
        item_count = cursor.fetchone()[0]
        
        print("\n" + "=" * 60)
        print("✓ Database seeded successfully!")
        print("=" * 60)
        print(f"Database: {DB_PATH}")
        print(f"Customers: {customer_count}")
        print(f"Stores: {cursor.execute('SELECT COUNT(*) FROM stores').fetchone()[0]}")
        print(f"Products: {cursor.execute('SELECT COUNT(*) FROM products').fetchone()[0]}")
        print(f"Orders: {order_count}")
        print(f"Order Items: {item_count}")
        print("\nYou can now use this database with the semantic layer!")
        print(f"Connection string: sqlite:///{DB_PATH.absolute()}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()



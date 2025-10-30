"""
Seed DuckDB database with retail sample data for semantic layer testing.

Creates tables and loads CSV data for customers, stores, products, orders, and order_items.
DuckDB can also read CSVs directly for quick testing.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import duckdb
except ImportError:
    print("❌ DuckDB not installed. Install with: pip install duckdb")
    sys.exit(1)

DB_PATH = Path("data/retail.duckdb")
SEED_DIR = Path("data/seed")


def create_and_load_tables(conn):
    """Create tables and load CSV data using DuckDB's efficient CSV reader."""
    
    # Customers
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS customers AS 
        SELECT * FROM read_csv_auto('{SEED_DIR}/customers.csv')
    """)
    print("✓ Loaded customers table")
    
    # Stores
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS stores AS 
        SELECT * FROM read_csv_auto('{SEED_DIR}/stores.csv')
    """)
    print("✓ Loaded stores table")
    
    # Products
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS products AS 
        SELECT * FROM read_csv_auto('{SEED_DIR}/products.csv')
    """)
    print("✓ Loaded products table")
    
    # Orders
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS orders AS 
        SELECT * FROM read_csv_auto('{SEED_DIR}/orders.csv')
    """)
    print("✓ Loaded orders table")
    
    # Order Items
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS order_items AS 
        SELECT * FROM read_csv_auto('{SEED_DIR}/order_items.csv')
    """)
    print("✓ Loaded order_items table")
    
    # Create indices
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_store ON orders(store_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id)")
    print("✓ Created indices")


def main():
    """Main seeding function."""
    print("=" * 60)
    print("Seeding DuckDB Retail Database")
    print("=" * 60)
    
    # Create database directory if needed
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if seed files exist
    if not SEED_DIR.exists():
        print(f"❌ Seed directory not found: {SEED_DIR}")
        print("Please ensure CSV files are in data/seed/")
        sys.exit(1)
    
    # Connect to database
    conn = duckdb.connect(str(DB_PATH))
    
    try:
        # Create and load tables
        create_and_load_tables(conn)
        
        # Verify data
        customer_count = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        store_count = conn.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
        product_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        order_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        item_count = conn.execute("SELECT COUNT(*) FROM order_items").fetchone()[0]
        
        print("\n" + "=" * 60)
        print("✓ Database seeded successfully!")
        print("=" * 60)
        print(f"Database: {DB_PATH}")
        print(f"Customers: {customer_count}")
        print(f"Stores: {store_count}")
        print(f"Products: {product_count}")
        print(f"Orders: {order_count}")
        print(f"Order Items: {item_count}")
        print("\nYou can now use this database with the semantic layer!")
        print(f"Connection string: duckdb:///{DB_PATH.absolute()}")
        print("\nExample queries:")
        print("  - What was our gross revenue last month?")
        print("  - Show me top 10 selling products")
        print("  - Count of orders by store")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()



import sys
import os

# Add root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Add fastapi_service to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fastapi_service'))

try:
    # Test imports
    from app.adapters.db.SQLiteAdapter import SQLiteAdapter
    
    # Test database connection
    adapter = SQLiteAdapter()
    conn = adapter._get_conn()
    print("✅ Successfully connected to database")
    print(f"   Database path: {adapter.db_path}")
    
    # Check if tables exist
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"   Tables found: {tables}")
    
    conn.close()
    print("✅ Database initialization successful!")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
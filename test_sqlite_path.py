import os
import sqlite3

# Set environment variable
os.environ["SQLITE_PATH"] = r"c:\HellenData\sqlite_store\hellencommerce.db"

# Ensure directory exists
db_dir = os.path.dirname(os.environ["SQLITE_PATH"])
if not os.path.exists(db_dir):
    os.makedirs(db_dir)

# Connect to SQLite database
conn = sqlite3.connect(os.environ["SQLITE_PATH"])
print(f"✅ Connected to SQLite database at: {os.environ['SQLITE_PATH']}")

# Create tables if they don't exist (same schema as before)
conn.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        user_id TEXT PRIMARY KEY,
        tipo TEXT,
        mercancia TEXT,
        estado TEXT,
        current_product_query TEXT,
        product_state TEXT,
        last_vendor TEXT,
        contexto TEXT,
        lat REAL,
        lon REAL,
        comm_status TEXT DEFAULT 'online',
        social_links TEXT,
        timestamp TEXT
    )
''')
conn.execute('''
    CREATE TABLE IF NOT EXISTS marketplace (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        tipo TEXT,
        nombre TEXT,
        mercancia TEXT,
        categoria_negocio TEXT,
        servicio TEXT,
        tags TEXT,
        tamaños TEXT,
        precio REAL,
        ubicacion TEXT,
        lat REAL,
        lon REAL,
        telefono TEXT,
        correo TEXT,
        contacto TEXT,
        domicilio INTEGER,
        estado TEXT,
        contexto TEXT,
        timestamp TEXT,
        acepta_notificaciones INTEGER,
        canal TEXT,
        preferencias TEXT,
        current_product_query TEXT,
        product_state TEXT,
        last_vendor TEXT,
        comm_status TEXT DEFAULT 'online',
        social_links TEXT
    )
''')
conn.execute('''
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        tipo TEXT,
        item TEXT,
        estado TEXT DEFAULT 'activo',
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.execute('''
    CREATE TABLE IF NOT EXISTS notificaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        tipo TEXT,
        mensaje TEXT,
        estado TEXT DEFAULT 'pendiente',
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fecha_envio TIMESTAMP,
        fecha_lectura TIMESTAMP
    )
''')
conn.commit()
conn.close()
print("✅ Database tables created successfully")
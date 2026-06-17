import sqlite3

def fill_timestamps(db_path="hellencommerce.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Rellenar registros sin timestamp
    cursor.execute("UPDATE usuarios SET timestamp = CURRENT_TIMESTAMP WHERE timestamp IS NULL;")
    conn.commit()

    # Mostrar los primeros 5 registros con su timestamp
    cursor.execute("SELECT user_id, mercancia, timestamp FROM usuarios LIMIT 5;")
    rows = cursor.fetchall()
    print("Primeros registros con timestamp:")
    for row in rows:
        print(row)

    conn.close()

if __name__ == "__main__":
    fill_timestamps()
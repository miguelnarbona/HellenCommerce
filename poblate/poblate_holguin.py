import sqlite3
import uuid

def populate():
    db_path = r"c:\HellenData\sqlite_store\hellencommerce.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Holguin, Cuba center
    lat_center, lng_center = 20.887, -76.263

    businesses = [
        (str(uuid.uuid4()), "Bodega La Central", lat_center + 0.002, lng_center + 0.001, "Calle Maceo #123", "555-0101"),
        (str(uuid.uuid4()), "Café Holguín", lat_center - 0.003, lng_center + 0.002, "Parque Calixto García", "555-0102"),
        (str(uuid.uuid4()), "Ferretería El Martillo", lat_center + 0.001, lng_center - 0.004, "Avenida de los Libertadores", "555-0103"),
        (str(uuid.uuid4()), "Tienda Panamericana", lat_center - 0.001, lng_center - 0.001, "Calle Libertad", "555-0104")
    ]

    for b in businesses:
        cur.execute("INSERT OR IGNORE INTO businesses (id, name, lat, lng, address, phone) VALUES (?, ?, ?, ?, ?, ?)", b)
        
        # Add some products for each business
        products = [
            ("dev-user", b[0], "Arroz (lb)", 25.0, "Arroz criollo de primera", None),
            ("dev-user", b[0], "Frijoles (lb)", 45.0, "Frijol negro fresco", None),
            ("dev-user", b[0], "Aceite (1L)", 250.0, "Aceite vegetal refinado", None)
        ]
        for p in products:
            cur.execute("INSERT INTO products (user_id, business_id, name, price, description, image) VALUES (?, ?, ?, ?, ?, ?)", p)

    conn.commit()
    conn.close()
    print("Base de datos poblada con negocios en Holguín.")

if __name__ == "__main__":
    populate()

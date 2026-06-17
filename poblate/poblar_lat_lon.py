import sqlite3
import platform
import os

# Coordenadas reales de TODAS las provincias de Cuba
COORDENADAS_PROVINCIAS = {
    "Pinar del Río": (22.4173, -83.6987),
    "Artemisa": (22.8133, -82.7619),
    "La Habana": (23.1136, -82.3666),
    "Mayabeque": (22.9870, -82.1511),
    "Matanzas": (23.0450, -81.5800),
    "Cienfuegos": (22.1460, -80.4350),
    "Villa Clara": (22.4930, -79.9660),
    "Sancti Spíritus": (21.9300, -79.4420),
    "Ciego de Ávila": (21.8400, -78.7610),
    "Camagüey": (21.3808, -77.9169),
    "Las Tunas": (20.9600, -76.9540),
    "Holguín": (20.8872, -76.2631),
    "Granma": (20.3833, -76.6413),
    "Santiago de Cuba": (20.0200, -75.8290),
    "Guantánamo": (20.1440, -75.2090),
    "Isla de la Juventud": (21.8833, -82.8000)
}

DB_PATH = r"c:\HellenData\sqlite_store\hellencommerce.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Leer todos los negocios
cur.execute("SELECT id, ubicacion FROM marketplace")
rows = cur.fetchall()

for row in rows:
    negocio_id = row[0]
    provincia = row[1]

    if provincia in COORDENADAS_PROVINCIAS:
        lat, lon = COORDENADAS_PROVINCIAS[provincia]

        cur.execute("""
            UPDATE marketplace
            SET lat = ?, lon = ?
            WHERE id = ?
        """, (lat, lon, negocio_id))

conn.commit()
conn.close()

print("Coordenadas de marketplace actualizadas correctamente.")

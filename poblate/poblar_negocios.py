import sqlite3
import json
from datetime import datetime

DB_PATH = "c:/HellenData/sqlite_store/hellencommerce.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# ============================================================
# LISTA DE NEGOCIOS (30)
# ============================================================

negocios = [
    # BARBERÍAS
    ("Barbería Elite", "barberia", "corte de pelo", ["barberia", "corte", "caballero"], "Calle 23 #456, Vedado", 20, "535-123-4567"),
    ("Corte Clásico", "barberia", "corte de pelo", ["barberia", "clasico"], "Avenida 10 #234, Playa", 15, "535-234-5678"),
    ("Barber Shop Habana", "barberia", "corte de pelo", ["moderno", "urbano"], "Calle Línea #789, Vedado", 25, "535-345-6789"),
    ("La Esquina del Barbero", "barberia", "corte de pelo", ["economico"], "Calle 17 #101, Plaza", 10, "535-456-7890"),
    ("Barbería Los Primos", "barberia", "corte de pelo", ["familiar"], "Calle 12 #55, Marianao", 18, "535-567-8901"),
    ("Barbería Central", "barberia", "corte de pelo", ["centro"], "Calle Neptuno #300, Centro Habana", 22, "535-678-9012"),

    # HELADERÍAS
    ("Heladería Coppelia", "heladeria", "venta de helado", ["dulce", "frio"], "Calle L #500, Vedado", 5, "535-789-0123"),
    ("Helados Varadero", "heladeria", "venta de helado", ["playa"], "Calle 1ra #100, Varadero", 4, "535-890-1234"),
    ("La Dulce Tentación", "heladeria", "venta de helado", ["artesanal"], "Calle 8 #200, Miramar", 6, "535-901-2345"),
    ("Helados Tropical", "heladeria", "venta de helado", ["tropical"], "Calle 3ra #345, Playa", 5, "535-012-3456"),
    ("Sabores del Caribe", "heladeria", "venta de helado", ["caribe"], "Calle 5ta #678, Habana del Este", 7, "535-123-4568"),
    ("Heladería La Estrella", "heladeria", "venta de helado", ["popular"], "Calle 19 #432, Plaza", 4, "535-234-5679"),

    # CAFETERÍAS
    ("Cafetería Aroma", "cafeteria", "venta de café", ["cafe", "desayuno"], "Calle 21 #123, Vedado", 10, "535-345-6780"),
    ("Café Habana", "cafeteria", "venta de café", ["tradicional"], "Calle Obispo #200, Habana Vieja", 12, "535-456-7891"),
    ("Café Express", "cafeteria", "venta de café", ["rapido"], "Calle 3ra #90, Playa", 8, "535-567-8902"),
    ("Café del Sol", "cafeteria", "venta de café", ["soleado"], "Calle 10 #345, Miramar", 9, "535-678-9013"),
    ("Café Central", "cafeteria", "venta de café", ["centro"], "Calle San Rafael #400, Centro Habana", 11, "535-789-0124"),
    ("Café La Esquina", "cafeteria", "venta de café", ["esquina"], "Calle 15 #222, Plaza", 7, "535-890-1235"),

    # PANADERÍAS
    ("Panadería La Espiga", "panaderia", "venta de pan", ["pan", "dulce"], "Calle 4 #123, Playa", 3, "535-901-2346"),
    ("Panadería El Molino", "panaderia", "venta de pan", ["tradicional"], "Calle 8 #456, Vedado", 4, "535-012-3457"),
    ("Panadería Santa María", "panaderia", "venta de pan", ["familiar"], "Calle 2 #789, Miramar", 3, "535-123-4569"),
    ("Panadería El Trigal", "panaderia", "venta de pan", ["trigo"], "Calle 6 #321, Marianao", 4, "535-234-5670"),
    ("Panadería Dulce Hogar", "panaderia", "venta de pan", ["dulce"], "Calle 9 #654, Plaza", 5, "535-345-6781"),
    ("Panadería Central", "panaderia", "venta de pan", ["centro"], "Calle 12 #987, Centro Habana", 3, "535-456-7892"),

    # FERRETERÍAS
    ("Ferretería El Tornillo", "ferreteria", "venta de herramientas", ["herramientas"], "Calle 7 #111, Vedado", 20, "535-567-8903"),
    ("Ferretería La Tuerca", "ferreteria", "venta de herramientas", ["tuercas"], "Calle 5 #222, Playa", 18, "535-678-9014"),
    ("Ferretería Industrial", "ferreteria", "venta de herramientas", ["industrial"], "Calle 3 #333, Marianao", 25, "535-789-0125"),
    ("Ferretería El Martillo", "ferreteria", "venta de herramientas", ["martillo"], "Calle 1 #444, Habana Vieja", 22, "535-890-1236"),
    ("Ferretería Central", "ferreteria", "venta de herramientas", ["centro"], "Calle 2 #555, Centro Habana", 19, "535-901-2347"),
    ("Ferretería El Obrero", "ferreteria", "venta de herramientas", ["obrero"], "Calle 4 #666, Plaza", 21, "535-012-3458"),
]

# ============================================================
# INSERTAR EN USUARIOS Y MARKETPLACE
# ============================================================

base_user_id = 70000000

for idx, (nombre, categoria, servicio, tags, ubicacion, precio, telefono) in enumerate(negocios):
    user_id = str(base_user_id + idx)

    # Insertar en usuarios
    cursor.execute("""
        INSERT INTO usuarios (user_id, tipo, nombre, mercancia, estado, contexto)
        VALUES (?, 'vendedor', ?, ?, 'activo', '')
    """, (user_id, nombre, categoria))

    # Insertar en marketplace
    cursor.execute("""
        INSERT INTO marketplace (
            user_id, tipo, nombre, mercancia, categoria_negocio, servicio, tags,
            precio, ubicacion, telefono, estado, timestamp
        )
        VALUES (?, 'vendedor', ?, ?, ?, ?, ?, ?, ?, ?, 'activo', ?)
    """, (
        user_id, nombre, categoria, categoria, servicio,
        json.dumps(tags), precio, ubicacion, telefono,
        datetime.now().isoformat()
    ))

conn.commit()
conn.close()

print("✔ Base de datos poblada con 30 negocios cruzados con usuarios.")

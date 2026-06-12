import sqlite3

def add_examples(db_path="c:/HellenData/sqlite_store/hellencommerce.db", cantidad=15):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Verificar que la tabla existe
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id TEXT PRIMARY KEY,
        tipo TEXT,
        nombre TEXT,
        mercancia TEXT,
        tamaños TEXT,
        precio REAL,
        ubicacion TEXT,
        telefono TEXT,
        correo TEXT,
        contacto TEXT,
        domicilio INTEGER,
        estado TEXT,
        contexto TEXT
    )
    """)

    # Buscar el último ID numérico
    cursor.execute("SELECT id FROM usuarios ORDER BY CAST(id AS INTEGER) DESC LIMIT 1")
    row = cursor.fetchone()
    ultimo_id = int(row[0]) if row else 60000000

    nuevos = []
    productos_vendedores = [
        ("Juego de sartenes antiadherentes", "Set de 3 piezas, color negro", 40.0, "La Habana"),
        ("Refrigerador Mabe", "9 pies, color plateado", 320.0, "Santiago de Cuba"),
        ("Teléfono móvil Samsung Galaxy A14", "128GB, color negro", 220.0, "Camagüey"),
        ("Bicicleta montañera", "Rodado 26, color azul", 150.0, "Holguín"),
        ("Cafetera eléctrica Oster", "1.5 litros, color negro", 65.0, "Santa Clara"),
        ("Colchón ortopédico", "2 plazas, espuma de alta densidad", 180.0, "Matanzas"),
        ("Zapatos deportivos Nike", "Talla 42, color blanco", 95.0, "Pinar del Río"),
    ]

    productos_compradores = [
        ("Lavadora automática LG", "8kg, color blanco", None, "La Habana"),
        ("Juego de comedor", "Mesa de madera con 6 sillas", None, "Santiago de Cuba"),
        ("Laptop HP Pavilion", "15 pulgadas, 8GB RAM, 512GB SSD", None, "Camagüey"),
        ("Televisor TCL", "40 pulgadas, SMART TV", None, "Holguín"),
        ("Motocicleta eléctrica", "Batería de litio, color rojo", None, "Santa Clara"),
        ("Aire acondicionado Split", "1 tonelada, color blanco", None, "Matanzas"),
        ("Cámara fotográfica Canon", "EOS Rebel T7, lente 18-55mm", None, "Pinar del Río"),
        ("Tablet Lenovo", "10 pulgadas, 64GB", None, "Cienfuegos"),
    ]

    # Generar registros alternando vendedor/comprador
    for i in range(cantidad):
        nuevo_id = str(ultimo_id + i + 1)
        if i % 2 == 0:  # vendedor
            prod = productos_vendedores[i % len(productos_vendedores)]
            tipo = "vendedor"
            nombre = f"Proveedor {i+1}"
            mercancia, tamaños, precio, ubicacion = prod
            telefono = nuevo_id
            correo = f"proveedor{i+1}@ejemplo.com"
            contacto = nombre
            domicilio = 0
            estado = "activo"
            contexto = f"USUARIO: Ofrezco {mercancia}, {tamaños}, disponible en {ubicacion}.\nIA: Entendido, lo registro."
        else:  # comprador
            prod = productos_compradores[i % len(productos_compradores)]
            tipo = "comprador"
            nombre = f"Cliente {i+1}"
            mercancia, tamaños, precio, ubicacion = prod
            telefono = nuevo_id
            correo = f"cliente{i+1}@ejemplo.com"
            contacto = nombre
            domicilio = 1
            estado = "activo"
            contexto = f"USUARIO: Estoy buscando {mercancia}, {tamaños}, en {ubicacion}.\nIA: Entendido, lo registro."

        nuevos.append((nuevo_id, tipo, nombre, mercancia, tamaños, precio,
                       ubicacion, telefono, correo, contacto, domicilio, estado, contexto))

    cursor.executemany("""
    INSERT OR REPLACE INTO usuarios
    (id, tipo, nombre, mercancia, tamaños, precio, ubicacion, telefono, correo, contacto, domicilio, estado, contexto)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, nuevos)

    conn.commit()
    conn.close()
    print(f"Se agregaron {cantidad} registros ficticios a la DB desde el ID {ultimo_id + 1}.")

if __name__ == "__main__":
    add_examples(cantidad=15)  # agrega 15 registros de prueba
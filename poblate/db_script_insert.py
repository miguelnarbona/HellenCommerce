import sqlite3

def add_more_examples(db_path="c:/HellenData/sqlite_store/hellencommerce.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    nuevos = [
        ("60000011", "vendedor", "Raúl Medina", "Arroz brasileño", "saco de 25kg", 22.0,
         "La Habana", "60000011", "raul.medina@ejemplo.com", "Raúl Medina", 1, "activo",
         "USUARIO: Tengo arroz brasileño en sacos de 25kg, buena calidad.\nIA: Entendido, lo registro."),

        ("60000012", "comprador", "Yanet Cruz", "Aceite de cocina", "botella 1L", None,
         "Holguín", "60000012", "yanet.cruz@ejemplo.com", "Yanet Cruz", 0, "activo",
         "USUARIO: Busco aceite de cocina en botellas de 1 litro.\nIA: Entendido, lo registro."),

        ("60000013", "vendedor", "Tomás Herrera", "Harina de trigo", "saco 50kg", 30.0,
         "Matanzas", "60000013", "tomas.herrera@ejemplo.com", "Tomás Herrera", 1, "activo",
         "USUARIO: Vendo harina de trigo en sacos de 50kg.\nIA: Entendido, lo registro."),

        ("60000014", "comprador", "Lidia Ramos", "Azúcar refino", "saco 25kg", None,
         "Santiago de Cuba", "60000014", "lidia.ramos@ejemplo.com", "Lidia Ramos", 1, "activo",
         "USUARIO: Necesito azúcar refino en sacos de 25kg.\nIA: Entendido, lo registro."),

        ("60000015", "vendedor", "Mario Pino", "Huevos frescos", "cartón 30 unidades", 4.5,
         "Villa Clara", "60000015", "mario.pino@ejemplo.com", "Mario Pino", 0, "activo",
         "USUARIO: Tengo huevos frescos por cartones de 30 unidades.\nIA: Entendido, lo registro."),

        ("60000016", "comprador", "Rosa Valdés", "Pollo congelado", "caja 10kg", None,
         "Camagüey", "60000016", "rosa.valdes@ejemplo.com", "Rosa Valdés", 1, "activo",
         "USUARIO: Busco pollo congelado por cajas.\nIA: Entendido, lo registro."),

        ("60000017", "vendedor", "Ernesto Suárez", "Frijoles negros", "saco 20kg", 18.0,
         "Pinar del Río", "60000017", "ernesto.suarez@ejemplo.com", "Ernesto Suárez", 1, "activo",
         "USUARIO: Vendo frijoles negros en sacos de 20kg.\nIA: Entendido, lo registro."),

        ("60000018", "comprador", "Julia Pérez", "Pasta alimenticia", "paquete 500g", None,
         "Cienfuegos", "60000018", "julia.perez@ejemplo.com", "Julia Pérez", 0, "activo",
         "USUARIO: Necesito pasta alimenticia en paquetes de 500g.\nIA: Entendido, lo registro."),

        ("60000019", "vendedor", "Omar Castillo", "Café molido", "paquete 250g", 6.0,
         "Las Tunas", "60000019", "omar.castillo@ejemplo.com", "Omar Castillo", 1, "activo",
         "USUARIO: Tengo café molido en paquetes de 250g.\nIA: Entendido, lo registro."),

        ("60000020", "comprador", "Daniela Soto", "Leche en polvo", "bolsa 1kg", None,
         "Bayamo", "60000020", "daniela.soto@ejemplo.com", "Daniela Soto", 1, "activo",
         "USUARIO: Busco leche en polvo en bolsas de 1kg.\nIA: Entendido, lo registro."),

        ("60000021", "vendedor", "Héctor Molina", "Mantequilla", "barra 250g", 2.5,
         "La Habana", "60000021", "hector.molina@ejemplo.com", "Héctor Molina", 1, "activo",
         "USUARIO: Vendo mantequilla en barras de 250g.\nIA: Entendido, lo registro."),

        ("60000022", "comprador", "Nora Iglesias", "Yogurt natural", "botella 1L", None,
         "Holguín", "60000022", "nora.iglesias@ejemplo.com", "Nora Iglesias", 0, "activo",
         "USUARIO: Necesito yogurt natural en botellas de 1 litro.\nIA: Entendido, lo registro."),

        ("60000023", "vendedor", "Felipe Torres", "Queso gouda", "pieza 1kg", 12.0,
         "Matanzas", "60000023", "felipe.torres@ejemplo.com", "Felipe Torres", 1, "activo",
         "USUARIO: Tengo queso gouda por piezas de 1kg.\nIA: Entendido, lo registro."),

        ("60000024", "comprador", "Irene Morales", "Jamón cocido", "paquete 500g", None,
         "Santiago de Cuba", "60000024", "irene.morales@ejemplo.com", "Irene Morales", 1, "activo",
         "USUARIO: Busco jamón cocido en paquetes de 500g.\nIA: Entendido, lo registro."),

        ("60000025", "vendedor", "Jorge Peña", "Pan suave", "bolsa 10 unidades", 1.8,
         "Villa Clara", "60000025", "jorge.pena@ejemplo.com", "Jorge Peña", 0, "activo",
         "USUARIO: Vendo pan suave en bolsas de 10 unidades.\nIA: Entendido, lo registro."),

        ("60000026", "comprador", "Carla Rivas", "Galletas dulces", "paquete 300g", None,
         "Camagüey", "60000026", "carla.rivas@ejemplo.com", "Carla Rivas", 1, "activo",
         "USUARIO: Necesito galletas dulces en paquetes de 300g.\nIA: Entendido, lo registro."),

        ("60000027", "vendedor", "Samuel Díaz", "Refresco gaseado", "botella 1.5L", 1.2,
         "Pinar del Río", "60000027", "samuel.diaz@ejemplo.com", "Samuel Díaz", 1, "activo",
         "USUARIO: Tengo refrescos gaseados en botellas de 1.5L.\nIA: Entendido, lo registro."),

        ("60000028", "comprador", "Patricia León", "Agua mineral", "botella 1.5L", None,
         "Cienfuegos", "60000028", "patricia.leon@ejemplo.com", "Patricia León", 0, "activo",
         "USUARIO: Busco agua mineral en botellas de 1.5L.\nIA: Entendido, lo registro."),

        ("60000029", "vendedor", "Ricardo Gómez", "Cerveza Cristal", "lata 355ml", 1.0,
         "Las Tunas", "60000029", "ricardo.gomez@ejemplo.com", "Ricardo Gómez", 1, "activo",
         "USUARIO: Vendo cerveza Cristal en latas.\nIA: Entendido, lo registro."),

        ("60000030", "comprador", "Elisa Fuentes", "Ron Havana Club", "botella 750ml", None,
         "Bayamo", "60000030", "elisa.fuentes@ejemplo.com", "Elisa Fuentes", 1, "activo",
         "USUARIO: Busco ron Havana Club en botellas de 750ml.\nIA: Entendido, lo registro."),

        ("60000031", "vendedor", "Adrián Pérez", "Papel sanitario", "paquete 12 rollos", 3.5,
         "La Habana", "60000031", "adrian.perez@ejemplo.com", "Adrián Pérez", 1, "activo",
         "USUARIO: Tengo papel sanitario en paquetes de 12 rollos.\nIA: Entendido, lo registro."),

        ("60000032", "comprador", "Marisol Vega", "Detergente líquido", "botella 2L", None,
         "Holguín", "60000032", "marisol.vega@ejemplo.com", "Marisol Vega", 0, "activo",
         "USUARIO: Necesito detergente líquido en botellas de 2L.\nIA: Entendido, lo registro."),

        ("60000033", "vendedor", "Diego Ramos", "Cloro doméstico", "botella 1L", 1.1,
         "Matanzas", "60000033", "diego.ramos@ejemplo.com", "Diego Ramos", 1, "activo",
         "USUARIO: Vendo cloro doméstico en botellas de 1L.\nIA: Entendido, lo registro."),

        ("60000034", "comprador", "Teresa López", "Esponjas de cocina", "paquete 3 unidades", None,
         "Santiago de Cuba", "60000034", "teresa.lopez@ejemplo.com", "Teresa López", 1, "activo",
         "USUARIO: Busco esponjas de cocina en paquetes de 3.\nIA: Entendido, lo registro."),

        ("60000035", "vendedor", "Humberto Silva", "Jabón de baño", "barra 200g", 1.0,
         "Villa Clara", "60000035", "humberto.silva@ejemplo.com", "Humberto Silva", 0, "activo",
         "USUARIO: Tengo jabón de baño en barras de 200g.\nIA: Entendido, lo registro."),
    ]

    cursor.executemany("""
    INSERT INTO usuarios
    (user_id, tipo, nombre, mercancia, tamaños, precio, ubicacion, telefono, correo, contacto, domicilio, estado, contexto)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, nuevos)

    conn.commit()
    conn.close()
    print("Se agregaron 25 registros nuevos (60000011–60000035).")


if __name__ == "__main__":
    add_more_examples()
import sqlite3
import random
import time

DB_PATH = "c:/HellenData/sqlite_store/hellencommerce.db"

VENDEDORES = [
    "Ricardo Gómez", "Luis Alberto Pérez", "Carlos Manuel Díaz", "Jorge Luis Hernández",
    "Yunior Martínez", "Reinier Castillo", "Yosvany Torres", "Michel Rodríguez",
    "Alejandro Pino", "Ernesto Cabrera", "Yadira López", "María Elena Pérez",
    "Claudia Hernández", "Yamila Rodríguez", "Lisandra Torres", "Dunia Morales",
    "Yanet González", "Rosa María Suárez", "Patricia León", "Liset Domínguez"
]

COMPRADORES = [
    "Daniel Morales", "Adrián Pérez", "Rafael Torres", "Eduardo Gómez",
    "Yordanis Rodríguez", "Abel Castillo", "Leonardo Díaz", "Mario Hernández",
    "Yisel López", "Dayana Pérez", "Laura González", "Yanet Cruz",
    "Claudia Suárez", "Roxana Morales", "Yamila León", "Lianet Torres",
    "María Fernanda Díaz", "Patricia Gómez", "Liset Hernández", "Dunia Pérez"
]


def actualizar_marketplace():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("→ Cargando registros existentes en marketplace...")

    cursor.execute("""
        SELECT id, tipo, mercancia, tamaños, ubicacion
        FROM marketplace
    """)
    rows = cursor.fetchall()

    print(f"→ {len(rows)} registros encontrados. Actualizando nombres...")

    for row in rows:
        registro_id, tipo, mercancia, tam, ubic = row

        if tipo == "vendedor":
            nombre = random.choice(VENDEDORES)
        else:
            nombre = random.choice(COMPRADORES)

        correo = nombre.lower().replace(" ", ".") + "@ejemplo.com"
        contacto = nombre

        contexto = (
            f"USUARIO: {'Vendo' if tipo=='vendedor' else 'Busco'} "
            f"{mercancia} {tam} en {ubic}.\nIA: Entendido."
        )

        cursor.execute("""
            UPDATE marketplace
            SET nombre = ?, contacto = ?, correo = ?, contexto = ?
            WHERE id = ?
        """, (nombre, contacto, correo, contexto, registro_id))

    conn.commit()
    conn.close()

    print("✔ marketplace actualizado correctamente con nombres reales.")


if __name__ == "__main__":
    actualizar_marketplace()

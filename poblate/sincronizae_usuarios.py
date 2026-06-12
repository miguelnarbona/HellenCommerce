import sqlite3
import time

DB_PATH = "c:/HellenData/sqlite_store/hellencommerce.db"


def sincronizar_usuarios_con_marketplace():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("→ Cargando registros de marketplace...")

    cursor.execute("""
        SELECT user_id, nombre, contacto, correo, contexto
        FROM marketplace
    """)
    marketplace_rows = cursor.fetchall()

    print(f"→ {len(marketplace_rows)} registros encontrados en marketplace.")
    print("→ Actualizando tabla usuarios...")

    actualizados = 0

    for row in marketplace_rows:
        user_id, nombre, contacto, correo, contexto = row

        # Actualizar usuarios con los datos reales del marketplace
        cursor.execute("""
            UPDATE usuarios
            SET nombre = ?, contacto = ?, correo = ?, contexto = ?
            WHERE user_id = ?
        """, (nombre, contacto, correo, contexto, user_id))

        actualizados += cursor.rowcount

    conn.commit()
    conn.close()

    print(f"✔ Sincronización completada. Registros actualizados en usuarios: {actualizados}")


if __name__ == "__main__":
    sincronizar_usuarios_con_marketplace()

import sqlite3

DB_PATH = "c:/HellenData/sqlite_store/hellencommerce.db"

def vaciar_base_de_datos():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Lista de tablas que quieres limpiar
    tablas = [
        "usuarios",
        "notificaciones",
        "historial",
        "productos",
        "mensajes",
        "interacciones"
    ]

    for tabla in tablas:
        try:
            cursor.execute(f"DELETE FROM {tabla}")
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{tabla}'")  # reset autoincrement
            print(f"✔ Tabla '{tabla}' vaciada.")
        except Exception as e:
            print(f"⚠ No se pudo limpiar la tabla '{tabla}': {e}")

    conn.commit()
    conn.close()
    print("\n🎉 Base de datos completamente vacía (estructura intacta).")


if __name__ == "__main__":
    vaciar_base_de_datos()

import sqlite3

def add_more_examples(db_path="c:/HellenData/sqlite_store/hellencommerce.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Inserta un registro de prueba
    cursor.execute("""
    INSERT INTO usuarios (
        user_id, tipo, nombre, mercancia, precio, ubicacion,
        telefono, correo, domicilio, estado
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "vendedor1", "vendedor", "Juan Pérez",
        "detergente líquido marca brillo",
        5.5, "Santiago de Cuba",
        "5551234", None, 0, "activo"
    ))

    conn.commit()
    conn.close()
    print("Se agregó un registro de prueba.")

if __name__ == "__main__":
    add_more_examples()
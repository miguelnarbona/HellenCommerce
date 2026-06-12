import sqlite3

def verificar_contexto(db_path: str, user_id: str):
    # Conectar a la base de datos
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Buscar el usuario por id
    cursor.execute("SELECT contexto FROM usuarios WHERE id = ?", (user_id,))
    row = cursor.fetchone()

    if row is None:
        print(f"⚠️ El usuario con id {user_id} no existe en la tabla.")
    else:
        contexto = row[0]
        if contexto:
            print(f"✅ Contexto del usuario {user_id}:")
            print(contexto)
        else:
            print(f"ℹ️ El usuario {user_id} existe pero su contexto está vacío.")

    conn.close()


# Ejemplo de uso
if __name__ == "__main__":
    # Cambia 'hellencommerce.db' por la ruta de tu base de datos
    db_path = "c:/HellenData/sqlite_store/hellencommerce.db"
    user_id = "12345678"
    verificar_contexto(db_path, user_id)
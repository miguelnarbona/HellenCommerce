import sqlite3
import platform
import os


def get_db_path():
    # 1. Si SQLITE_PATH está definido → siempre tiene prioridad
    env_path = os.getenv("SQLITE_PATH")
    if env_path:
        return env_path

    # 2. Detectar sistema operativo
    sistema = platform.system().lower()

    if "windows" in sistema:
        # Ruta por defecto en Windows
        return f"C:/HellenData/sqlite_store/hellencommerce.db"

    if "linux" in sistema:
        # Ruta por defecto en Linux (contenedor o servidor)
        return "/HellenData/sqlite_store/hellencommerce.db"

    # 3. Fallback universal
    return "hellencommerce.db"

def clean_database():
    DB_PATH = get_db_path()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(">>> Iniciando limpieza inteligente de la tabla 'usuarios'...")

    # 1. Eliminar mercancías vacías o desconocidas
    cursor.execute("""
        DELETE FROM usuarios
        WHERE mercancia IS NULL
           OR TRIM(mercancia) = ''
           OR LOWER(mercancia) = 'desconocido';
    """)

    # 2. Eliminar mercancías con palabras de interacción
    cursor.execute("""
        DELETE FROM usuarios
        WHERE LOWER(mercancia) LIKE '%dame%'
           OR LOWER(mercancia) LIKE '%pasa%'
           OR LOWER(mercancia) LIKE '%pasame%'
           OR LOWER(mercancia) LIKE '%pásame%'
           OR LOWER(mercancia) LIKE '%detalles%'
           OR LOWER(mercancia) LIKE '%detalle%'
           OR LOWER(mercancia) LIKE '%datos%'
           OR LOWER(mercancia) LIKE '%ok%'
           OR LOWER(mercancia) LIKE '%gracias%'
           OR LOWER(mercancia) LIKE '%si%'
           OR LOWER(mercancia) LIKE '%sí%';
    """)

    # 3. Eliminar mercancías contaminadas por el bug anterior
    cursor.execute("""
        DELETE FROM usuarios
        WHERE LOWER(mercancia) LIKE '%algun vendedor%'
           OR LOWER(mercancia) LIKE '%algún vendedor%'
           OR LOWER(mercancia) LIKE '%otro vendedor%';
    """)

    # 4. Eliminar mercancías que contienen verbos de conversación
    cursor.execute("""
        DELETE FROM usuarios
        WHERE LOWER(mercancia) LIKE '%quiero%'
           OR LOWER(mercancia) LIKE '%busco%'
           OR LOWER(mercancia) LIKE '%necesito%'
           OR LOWER(mercancia) LIKE '%tengo%'
           OR LOWER(mercancia) LIKE '%hola%'
           OR LOWER(mercancia) LIKE '%buenas%';
    """)

    # 5. Eliminar mercancías demasiado cortas para ser productos reales
    cursor.execute("""
        DELETE FROM usuarios
        WHERE LENGTH(mercancia) < 3;
    """)

    conn.commit()
    conn.close()

    print(">>> Limpieza completada con éxito.")
    print(">>> La base de datos está ahora libre de contaminación.")


if __name__ == "__main__":
    clean_database()

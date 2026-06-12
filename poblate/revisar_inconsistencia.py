import sqlite3
import json

DB_PATH = "c:/HellenData/sqlite_store/hellencommerce.db"


def verificar_bd():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n==============================")
    print("   VERIFICADOR DE BASE DE DATOS")
    print("==============================\n")

    # -----------------------------
    # 1. Usuarios sin marketplace
    # -----------------------------
    print("→ Usuarios sin registros en marketplace:")
    cursor.execute("""
        SELECT user_id, nombre, tipo
        FROM usuarios
        WHERE user_id NOT IN (SELECT user_id FROM marketplace)
    """)
    rows = cursor.fetchall()
    for r in rows:
        print("  -", r)
    if not rows:
        print("  ✔ Ninguno")

    print("\n→ Marketplace sin usuario correspondiente:")
    cursor.execute("""
        SELECT user_id, nombre, tipo
        FROM marketplace
        WHERE user_id NOT IN (SELECT user_id FROM usuarios)
    """)
    rows = cursor.fetchall()
    for r in rows:
        print("  -", r)
    if not rows:
        print("  ✔ Ninguno")

    # -----------------------------
    # 2. Vendedores sin mercancía
    # -----------------------------
    print("\n→ Vendedores sin mercancía:")
    cursor.execute("""
        SELECT user_id, nombre
        FROM marketplace
        WHERE tipo='vendedor' AND (mercancia IS NULL OR mercancia='')
    """)
    rows = cursor.fetchall()
    for r in rows:
        print("  -", r)
    if not rows:
        print("  ✔ Ninguno")

    # -----------------------------
    # 3. Compradores sin mercancía
    # -----------------------------
    print("\n→ Compradores sin mercancía:")
    cursor.execute("""
        SELECT user_id, nombre
        FROM marketplace
        WHERE tipo='comprador' AND (mercancia IS NULL OR mercancia='')
    """)
    rows = cursor.fetchall()
    for r in rows:
        print("  -", r)
    if not rows:
        print("  ✔ Ninguno")

    # -----------------------------
    # 4. Correos inválidos
    # -----------------------------
    print("\n→ Correos inválidos:")
    cursor.execute("""
        SELECT user_id, correo
        FROM marketplace
        WHERE correo NOT LIKE '%@%.%'
    """)
    rows = cursor.fetchall()
    for r in rows:
        print("  -", r)
    if not rows:
        print("  ✔ Ninguno")

    # -----------------------------
    # 5. Contextos vacíos o incoherentes
    # -----------------------------
    print("\n→ Contextos vacíos o incoherentes:")
    cursor.execute("""
        SELECT user_id, nombre, contexto
        FROM marketplace
        WHERE contexto IS NULL OR contexto=''
           OR contexto NOT LIKE 'USUARIO:%'
    """)
    rows = cursor.fetchall()
    for r in rows:
        print("  -", r)
    if not rows:
        print("  ✔ Ninguno")

    # -----------------------------
    # 6. Duplicados por user_id
    # -----------------------------
    print("\n→ Duplicados por user_id en marketplace:")
    cursor.execute("""
        SELECT user_id, COUNT(*)
        FROM marketplace
        GROUP BY user_id
        HAVING COUNT(*) > 1
    """)
    rows = cursor.fetchall()
    for r in rows:
        print("  -", r)
    if not rows:
        print("  ✔ Ninguno")

    # -----------------------------
    # 7. Usuarios con last_vendor corrupto
    # -----------------------------
    print("\n→ Usuarios con last_vendor corrupto:")
    cursor.execute("""
        SELECT user_id, last_vendor
        FROM usuarios
        WHERE last_vendor IS NOT NULL
    """)
    rows = cursor.fetchall()
    corruptos = 0
    for user_id, lv in rows:
        try:
            json.loads(lv)
        except:
            print("  -", user_id, "(last_vendor inválido)")
            corruptos += 1
    if corruptos == 0:
        print("  ✔ Ninguno")

    # -----------------------------
    # 8. Nombres genéricos
    # -----------------------------
    print("\n→ Registros con nombres genéricos:")
    cursor.execute("""
        SELECT user_id, nombre
        FROM marketplace
        WHERE nombre LIKE 'Vendedor %' OR nombre LIKE 'Comprador %'
    """)
    rows = cursor.fetchall()
    for r in rows:
        print("  -", r)
    if not rows:
        print("  ✔ Ninguno")

    conn.close()
    print("\n✔ Verificación completada.\n")


if __name__ == "__main__":
    verificar_bd()

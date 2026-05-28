# app/adapters/db/PostgreSQLAdapter.py

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any


class PostgreSQLAdapter:
    """
    Adaptador PostgreSQL compatible con SQLiteAdapter.
    Preparado para alta concurrencia y producción real.
    """

    def __init__(self,
                 host: str = "localhost",
                 port: int = 5432,
                 user: str = "postgres",
                 password: str = "postgres",
                 database: str = "broker_db"):

        self.conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=database
        )
        self.conn.autocommit = True

        self._create_tables()

    # ---------------------------------------------------------
    # Crear tablas si no existen
    # ---------------------------------------------------------
    def _create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                tipo TEXT NOT NULL,
                mercancia TEXT,
                precio TEXT,
                ubicacion TEXT,
                telefono TEXT,
                correo TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON usuarios (user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tipo ON usuarios (tipo);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mercancia ON usuarios (mercancia);")

    # ---------------------------------------------------------
    # Registrar usuario / interacción
    # ---------------------------------------------------------
    def registrar_usuario(self, data: Dict[str, Any]):
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO usuarios (user_id, tipo, mercancia, precio, ubicacion, telefono, correo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get("user_id"),
            data.get("tipo"),
            data.get("mercancia"),
            data.get("precio"),
            data.get("ubicacion"),
            data.get("telefono"),
            data.get("correo")
        ))

    # ---------------------------------------------------------
    # Buscar coincidencias exactas
    # ---------------------------------------------------------
    def buscar_coincidencias(self, tipo_opuesto: str, mercancia: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT *
            FROM usuarios
            WHERE tipo = %s
              AND mercancia ILIKE %s
            ORDER BY timestamp DESC
            LIMIT 10
        """, (tipo_opuesto, f"%{mercancia}%"))

        return cursor.fetchall()

    # ---------------------------------------------------------
    # Historial por usuario
    # ---------------------------------------------------------
    def obtener_historial_usuario(self, user_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT *
            FROM usuarios
            WHERE user_id = %s
            ORDER BY timestamp DESC
            LIMIT 20
        """, (user_id,))

        return cursor.fetchall()

    # ---------------------------------------------------------
    # Cerrar conexión
    # ---------------------------------------------------------
    def close(self):
        try:
            self.conn.close()
        except:
            pass
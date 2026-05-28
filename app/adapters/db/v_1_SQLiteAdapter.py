# app/adapters/db/SQLiteAdapter.py

import sqlite3
import os
import unicodedata
from typing import List, Dict, Any


class SQLiteAdapter:
    """
    Adaptador SQLite optimizado para concurrencia (modo WAL).
    Preparado para migrar a PostgreSQL sin cambiar el resto del sistema.
    Usa conexión por operación para evitar problemas de cursores recursivos.
    Incluye soporte para current_product_query (memoria semántica).
    """

    # Stopwords para limpiar búsquedas
    STOPWORDS = {
        "algun", "algún", "alguna", "algunas", "algunos",
        "vendedor", "vendedora", "vendedores", "vendedoras",
        "busco", "compro", "quiero", "necesito", "tengo",
        "vendo", "ofrezco", "otro", "otra", "otros", "otras",
        "dame", "pasame", "pásame", "datos", "detalles",
        "un", "una", "unos", "unas", "el", "la", "los", "las",
        "por", "para", "con", "sin", "de", "del", "en", "a",
        "y", "o", "u", "que", "si", "sí", "ok"
    }

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.getenv("SQLITE_PATH")

        if not self.db_path:
            raise ValueError("SQLITE_PATH no está definido en las variables de entorno")

        self._init_db()

    # ---------------------------------------------------------
    # Helpers de conexión
    # ---------------------------------------------------------
    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        try:
            self._enable_wal(conn)
            self._create_tables(conn)
            self._ensure_current_product_query_column(conn)
        finally:
            conn.close()

    # ---------------------------------------------------------
    # Activar WAL
    # ---------------------------------------------------------
    def _enable_wal(self, conn: sqlite3.Connection):
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
        except Exception:
            pass

    # ---------------------------------------------------------
    # Crear tablas
    # ---------------------------------------------------------
    def _create_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()

        # Tabla usuarios
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                tipo TEXT NOT NULL,
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
                contexto TEXT,
                acepta_notificaciones INTEGER DEFAULT 0,
                canal TEXT,
                preferencias TEXT,
                product_state TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON usuarios (user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tipo ON usuarios (tipo);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mercancia ON usuarios (mercancia);")

        # Tabla notificaciones
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notificaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                tipo TEXT NOT NULL,
                mensaje TEXT NOT NULL,
                estado TEXT DEFAULT 'pendiente',
                fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                fecha_envio DATETIME,
                fecha_lectura DATETIME
            );
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notif_user ON notificaciones (user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notif_estado ON notificaciones (estado);")

        # Tabla conversaciones
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                titulo TEXT,
                es_flag INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            );
        """)

        # Tabla mensajes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                rol TEXT NOT NULL,
                contenido TEXT NOT NULL,
                created_at TEXT,
                FOREIGN KEY(conversation_id) REFERENCES conversaciones(id)
            );
        """)

        # Tabla products
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                business_id TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                description TEXT,
                image TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Tabla businesses
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS businesses (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                lat REAL NOT NULL,
                lng REAL NOT NULL,
                address TEXT,
                phone TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_business_lat ON businesses (lat);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_business_lng ON businesses (lng);")

        conn.commit()

    # ---------------------------------------------------------
    # Asegurar columna current_product_query
    # ---------------------------------------------------------
    def _ensure_current_product_query_column(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(usuarios);")
        columnas = [row["name"] for row in cursor.fetchall()]

        if "current_product_query" not in columnas:
            cursor.execute("""
                ALTER TABLE usuarios
                ADD COLUMN current_product_query TEXT;
            """)
            conn.commit()

    # ---------------------------------------------------------
    # Normalización avanzada
    # ---------------------------------------------------------
    def _normalize(self, text: str) -> List[str]:
        if not text:
            return []

        # Quitar acentos
        text = unicodedata.normalize("NFD", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")

        # Minúsculas y limpieza
        text = text.lower()
        for p in ",.;:!?¿¡()[]{}":
            text = text.replace(p, " ")

        tokens = text.split()

        # Filtrar stopwords y tokens cortos
        tokens = [t for t in tokens if len(t) > 2 and t not in self.STOPWORDS]

        return tokens

    # ---------------------------------------------------------
    # Buscar coincidencias tokenizadas
    # ---------------------------------------------------------
    def buscar_coincidencias(self, tipo: str, mercancia: str) -> List[Dict[str, Any]]:
        if not mercancia:
            return []

        tokens = self._normalize(mercancia)

        if not tokens:
            return []

        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            condiciones = " OR ".join(["LOWER(mercancia) LIKE '%' || ? || '%'"] * len(tokens))

            query = f"""
                SELECT *
                FROM usuarios
                WHERE tipo = ?
                AND estado = 'activo'
                AND ({condiciones})
                ORDER BY timestamp DESC
                LIMIT 10
            """

            cursor.execute(query, [tipo] + tokens)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        finally:
            conn.close()

    # ---------------------------------------------------------
    # Historial
    # ---------------------------------------------------------
    def obtener_historial_usuario(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT *
                FROM usuarios
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT 20
            """, (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ---------------------------------------------------------
    # Registrar usuario
    # ---------------------------------------------------------
    def registrar_usuario(self, data: Dict[str, Any]):
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO usuarios (
                    user_id, tipo, nombre, mercancia, tamaños, precio,
                    ubicacion, telefono, correo, contacto, domicilio,
                    estado, contexto, current_product_query
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("user_id"),
                data.get("tipo"),
                data.get("nombre"),
                data.get("mercancia"),
                data.get("tamaños"),
                data.get("precio"),
                data.get("ubicacion"),
                data.get("telefono"),
                data.get("correo"),
                data.get("contacto"),
                data.get("domicilio"),
                data.get("estado", "activo"),
                data.get("contexto"),
                data.get("current_product_query")
            ))
            conn.commit()
        finally:
            conn.close()

    # ---------------------------------------------------------
    # Registrar notificación
    # ---------------------------------------------------------
    def registrar_notificacion(self, data: Dict[str, Any]):
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, mensaje)
                VALUES (?, ?, ?)
            """, (
                data.get("user_id"),
                data.get("tipo"),
                data.get("mensaje")
            ))
            conn.commit()
        finally:
            conn.close()

    # ---------------------------------------------------------
    # Obtener notificaciones pendientes
    # ---------------------------------------------------------
    def obtener_notificaciones_pendientes(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT *
                FROM notificaciones
                WHERE estado = 'pendiente'
                ORDER BY fecha_creacion ASC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ---------------------------------------------------------
    # Marcar notificación enviada
    # ---------------------------------------------------------
    def marcar_notificacion_enviada(self, notif_id: int):
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE notificaciones
                SET estado = 'enviada',
                    fecha_envio = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (notif_id,))
            conn.commit()
        finally:
            conn.close()

    # ---------------------------------------------------------
    # Obtener último estado de usuario
    # ---------------------------------------------------------
    def obtener_usuario(self, user_id: str) -> Dict[str, Any] | None:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, nombre, telefono, correo,
                       acepta_notificaciones, canal, preferencias
                FROM usuarios
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (user_id,))
            row = cursor.fetchone()

            if row:
                return {
                    "user_id": row["user_id"],
                    "nombre": row["nombre"],
                    "telefono": row["telefono"],
                    "correo": row["correo"],
                    "acepta_notificaciones": row["acepta_notificaciones"],
                    "canal": row["canal"],
                    "preferencias": row["preferencias"]
                }

            return None
        finally:
            conn.close()

    # ---------------------------------------------------------
    # Actualizar usuario
    # ---------------------------------------------------------
    def actualizar_usuario(self, user_id: str, data: dict):
        campos = []
        valores: list[Any] = []

        for k, v in data.items():
            if v is not None:
                campos.append(f"{k} = ?")
                valores.append(v)

        if not campos:
            return

        valores.append(user_id)

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE usuarios
                SET {", ".join(campos)}
                WHERE user_id = ?
            """, valores)
            conn.commit()
        finally:
            conn.close()

    def update_user_state(self, user_id, current_product_query=None, product_state=None, last_vendor=None):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE usuarios
            SET current_product_query = COALESCE(?, current_product_query),
                product_state = COALESCE(?, product_state),
                last_vendor = COALESCE(?, last_vendor)
            WHERE user_id = ?
        """, (
            current_product_query,
            product_state,
            json.dumps(last_vendor) if last_vendor else None,
            user_id
        ))

        conn.commit()
        conn.close()


    def get_user_state(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT current_product_query, product_state, last_vendor
            FROM usuarios
            WHERE user_id = ?
        """, (user_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "current_product_query": row[0],
            "product_state": row[1],
            "last_vendor": json.loads(row[2]) if row[2] else None
        }

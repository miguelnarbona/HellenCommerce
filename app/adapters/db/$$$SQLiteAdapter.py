# adapters/db/SQLiteAdapter.py

import sqlite3
from adapters.db.IDatabaseAdapter import IDatabaseAdapter


class SQLiteAdapter(IDatabaseAdapter):
    """
    Adaptador SQLite robusto para la base de datos de usuarios.
    - Maneja creación de tabla.
    - Inserción y actualización de usuarios.
    - Búsquedas flexibles por SQL.
    - Búsqueda semántica opcional vía RAG.
    """

    def __init__(self, db_path="hellencommerce.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # ← filas como diccionarios
        self.cursor = self.conn.cursor()
        self._create_table()

    # ---------------------------------------------------------
    # CREACIÓN DE TABLA
    # ---------------------------------------------------------
    def _create_table(self):
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY,
            tipo TEXT,
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
            contexto TEXT
        )
        """)
        self.conn.commit()

    # ---------------------------------------------------------
    # INSERCIÓN / ACTUALIZACIÓN
    # ---------------------------------------------------------
    def insert_user(self, data: dict):
        """
        Inserta o actualiza un usuario en la tabla.
        Maneja valores faltantes y normaliza entradas.
        """

        self.cursor.execute("""
        INSERT OR REPLACE INTO usuarios
        (id, tipo, nombre, mercancia, tamaños, precio, ubicacion, telefono, correo, contacto, domicilio, estado, contexto)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("id"),
            data.get("tipo"),
            data.get("nombre"),
            data.get("mercancia"),
            data.get("tamaños", ""),
            data.get("precio"),
            data.get("ubicacion", "N/A"),
            data.get("telefono"),
            data.get("correo"),
            data.get("contacto"),
            data.get("domicilio", 0),
            data.get("estado", "activo"),
            data.get("contexto", "")
        ))
        self.conn.commit()

    # ---------------------------------------------------------
    # BÚSQUEDA SEMÁNTICA (RAG)
    # ---------------------------------------------------------
    def search_matches_semantic(self, tipo, mercancia, rag, embedder):
        """
        Búsqueda semántica usando embeddings + Chroma.
        Filtra por tipo contrario.
        """
        if not mercancia or mercancia == "desconocido":
            return []

        emb = embedder.embed(mercancia)
        results = rag.query(emb, n_results=5)

        opposite = "vendedor" if tipo == "comprador" else "comprador"

        return [
            r for r in results
            if r["metadata"].get("tipo") == opposite
        ]

    # ---------------------------------------------------------
    # BÚSQUEDA SQL FLEXIBLE
    # ---------------------------------------------------------
    def search_matches(self, tipo: str, mercancia: str, precio=None, tamanos=None, ubicacion=None):
        """
        Búsqueda flexible:
        - Coincidencias parciales por texto
        - Tokens de mercancia
        - Rango de precio
        - Tamaños
        - Ubicación
        """

        # -----------------------------
        # 1. Tokens de texto
        # -----------------------------
        tokens = []
        if mercancia and mercancia != "desconocido":
            tokens = [t.strip() for t in mercancia.lower().split() if len(t.strip()) > 2]

        text_conditions = []
        text_params = []

        if tokens:
            text_conditions = ["LOWER(mercancia) LIKE ?" for _ in tokens]
            text_params = [f"%{t}%" for t in tokens]

        # -----------------------------
        # 2. Filtros adicionales
        # -----------------------------
        extra_conditions = []
        extra_params = []

        if precio:
            extra_conditions.append("precio <= ?")
            extra_params.append(precio)

        if tamanos:
            extra_conditions.append("LOWER(tamaños) LIKE ?")
            extra_params.append(f"%{tamanos.lower()}%")

        if ubicacion:
            extra_conditions.append("LOWER(ubicacion) LIKE ?")
            extra_params.append(f"%{ubicacion.lower()}%")

        # -----------------------------
        # 3. WHERE dinámico
        # -----------------------------
        where_clauses = []

        # Tipo contrario
        where_clauses.append("tipo != ?")
        params = [tipo]

        # Estado activo
        where_clauses.append("estado = 'activo'")

        # Texto
        if text_conditions:
            where_clauses.append("(" + " OR ".join(text_conditions) + ")")
            params.extend(text_params)

        # Filtros extra
        if extra_conditions:
            where_clauses.append("(" + " AND ".join(extra_conditions) + ")")
            params.extend(extra_params)

        where_sql = " AND ".join(where_clauses)

        query = f"""
            SELECT *
            FROM usuarios
            WHERE {where_sql}
            ORDER BY ROWID DESC
            LIMIT 20
        """

        return self.conn.execute(query, params).fetchall()

    # ---------------------------------------------------------
    # OBSOLETO
    # ---------------------------------------------------------
    def process_prompt(self, message: str, role: str, user_id: str) -> dict:
        raise NotImplementedError("La lógica se maneja en BusinessLogic.")
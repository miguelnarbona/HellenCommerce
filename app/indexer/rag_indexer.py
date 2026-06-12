# rag_indexer.py

class RAGIndexer:
    """
    Servicio de indexación para sincronizar registros de SQLite hacia ChromaDB (HTTP).
    - Construye textos enriquecidos para embeddings.
    - Evita duplicados mediante doc_id determinístico.
    - Permite indexación completa o incremental.
    """

    def __init__(self, db, rag, embedder):
        self.db = db
        self.rag = rag
        self.embedder = embedder

    # ---------------------------------------------------------
    # Construcción del texto semántico
    # ---------------------------------------------------------
    def _build_text(self, row):
        """
        Construye un texto enriquecido para indexación semántica.
        Más descriptivo para mejorar recuperación.
        """
        return (
            f"[Usuario {row['id']}] "
            f"Tipo: {row['tipo']}. "
            f"Mercancía: {row['mercancia']}. "
            f"Precio: {row['precio']}. "
            f"Ubicación: {row['ubicacion']}. "
            f"Tamaños: {row['tamaños']}. "
            f"Domicilio: {row['domicilio']}. "
            f"Contexto previo: {row['contexto']}"
        )

    # ---------------------------------------------------------
    # Generación de doc_id único y estable
    # ---------------------------------------------------------
    def _generate_doc_id(self, row):
        """
        Genera un doc_id determinístico basado en los campos clave.
        """
        base = f"{row['id']}_{row['tipo']}_{row['mercancia']}"
        return base.replace(" ", "_").lower()

    # ---------------------------------------------------------
    # Indexar una sola fila
    # ---------------------------------------------------------
    def index_row(self, row):
        """
        Indexa un registro individual en Chroma.
        """
        if not row:
            return

        doc_id = self._generate_doc_id(row)
        texto = self._build_text(row)
        embedding = self.embedder.embed(texto)

        self.rag.add_document(
            doc_id=doc_id,
            text=texto,
            embedding=embedding,
            metadata={
                "user_id": row["id"],
                "tipo": row["tipo"],
                "mercancia": row["mercancia"],
                "fuente": "sqlite",
                "indexado": "registro_usuario"
            }
        )

    # ---------------------------------------------------------
    # Sincronización completa
    # ---------------------------------------------------------
    def sync_all(self):
        """
        Sincroniza todos los registros de SQLite hacia Chroma.
        Solo indexa los que no existen aún.
        """
        rows = self.db.conn.execute("SELECT * FROM usuarios").fetchall()

        for row in rows:
            doc_id = self._generate_doc_id(row)

            # Verificar si ya existe en Chroma
            existing = self.rag.collection.get(ids=[doc_id])
            if existing["ids"]:
                continue

            self.index_row(row)

        return True

    # ---------------------------------------------------------
    # Sincronización incremental
    # ---------------------------------------------------------
    def sync_new(self):
        """
        Indexa únicamente los registros que aún no están en Chroma.
        """
        return self.sync_all()
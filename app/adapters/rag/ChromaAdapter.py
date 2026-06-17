"""
HellenCommerce - VectorAdapter  (expuesto como ChromaAdapter)
Router híbrido: ChromaDB local  ←→  Qdrant Cloud (GCP).

Conmutación en caliente mediante variable de entorno:
  VECTOR_DB_TYPE = "chromadb"  (default) → _ChromaBackend  (lógica original)
  VECTOR_DB_TYPE = "qdrant"              → _QdrantBackend   (nuevo)

Interfaz pública idéntica al ChromaAdapter original:
  add_document(doc_id, text, embedding, metadata)
  query(embedding, n_results, where)  →  list[dict]

Filtros:
  - QueryAdapter construye filtros en el formato nativo de cada backend.
  - _QdrantBackend.query() acepta tanto dict (lo traduce) como un objeto
    Filter ya construido (lo usa directamente). Capa defensiva polimórfica.

Variables de entorno (Qdrant):
  QDRANT_URL      — URL del cluster Qdrant Cloud
  QDRANT_API_KEY  — API Key de Qdrant Cloud
"""

import os
import uuid
import platform


# ============================================================
# Backend ChromaDB  (lógica original, sin cambios funcionales)
# ============================================================
class _ChromaBackend:

    def __init__(self, collection_name: str):
        system = platform.system()
        host   = os.getenv("CHROMA_HOST", "127.0.0.1" if system == "Windows" else "chromadb_service")
        port   = int(os.getenv("CHROMA_PORT", 8001))

        print(f"=== CHROMA BACKEND ===  HOST:{host}  PORT:{port}", flush=True)

        from chromadb import HttpClient
        client = HttpClient(host=host, port=port)
        self.collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )

    def add_document(self, doc_id: str, text: str, embedding: list, metadata: dict = None):
        self.collection.add(
            ids=[doc_id],
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata or {}],
        )

    def query(self, embedding: list, n_results: int = 3, where: dict = None) -> list:
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
        )
        docs  = results.get("documents", [[]])[0]
        metas = results.get("metadatas",  [[]])[0]
        ids   = results.get("ids",        [[]])[0]
        return [
            {"id": ids[i], "text": docs[i], "metadata": metas[i]}
            for i in range(len(docs))
        ]


# ============================================================
# Backend Qdrant Cloud  (nuevo)
# ============================================================
class _QdrantBackend:

    VECTOR_DIM = 384

    def __init__(self, collection_name: str):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        url     = os.getenv("QDRANT_URL", "").strip()
        api_key = os.getenv("QDRANT_API_KEY", "").strip()

        if not url:
            raise EnvironmentError(
                "QDRANT_URL no está definida. "
                "Añádela al entorno o al archivo .env para usar el backend Qdrant."
            )

        self.collection_name = collection_name
        self.client = QdrantClient(url=url, api_key=api_key or None)

        # Crear colección si no existe (idempotente)
        existing_names = [c.name for c in self.client.get_collections().collections]
        if collection_name not in existing_names:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.VECTOR_DIM,
                    distance=Distance.COSINE,
                ),
            )
            print(f"✅ Colección Qdrant '{collection_name}' creada (384d / COSINE).", flush=True)
        else:
            print(f"✅ Colección Qdrant '{collection_name}' ya existe.", flush=True)

    # ---- Helpers internos ----

    @staticmethod
    def _str_to_uuid(doc_id: str) -> str:
        """
        Convierte cualquier string ID a UUID v5 determinista.
        Qdrant requiere UUIDs válidos como point IDs.
        El ID original se preserva en el payload bajo la clave 'doc_id'.
        """
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_id))

    @staticmethod
    def _resolve_filter(where):
        """
        Resuelve el filtro para Qdrant de forma polimórfica:

          - Si where es None o vacío → retorna None (sin filtro).
          - Si where es ya un objeto Filter de Qdrant (construido por QueryAdapter)
            → lo usa directamente, sin doble traducción.
          - Si where es un dict (llamada directa desde ContextManager u otro caller)
            → lo traduce a Filter con FieldCondition+MatchValue por cada par.

        Esto garantiza compatibilidad con todos los callers, independientemente
        de si construyen el filtro ellos mismos o delegan la traducción aquí.
        """
        if not where:
            return None

        from qdrant_client.models import Filter, FieldCondition, MatchValue

        # Ya es un Filter nativo → usar directamente
        if isinstance(where, Filter):
            return where

        # Es un dict → traducir
        conditions = [
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in where.items()
        ]
        return Filter(must=conditions)

    # ---- Interfaz pública ----

    def add_document(self, doc_id: str, text: str, embedding: list, metadata: dict = None):
        from qdrant_client.models import PointStruct
        meta = metadata or {}

        # Payload estructurado: user_id, tipo, fuente + resto de metadata
        payload = {
            "doc_id":  doc_id,
            "text":    text,
            "user_id": meta.get("user_id", ""),
            "tipo":    meta.get("tipo", ""),
            "fuente":  meta.get("fuente", ""),
        }
        extras = {k: v for k, v in meta.items() if k not in ("user_id", "tipo", "fuente")}
        payload.update(extras)

        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(
                id=self._str_to_uuid(doc_id),
                vector=embedding,
                payload=payload,
            )],
        )

    def query(self, embedding: list, n_results: int = 3, where=None) -> list:
        """
        Busca por similitud vectorial aplicando el filtro resuelto.

        Acepta `where` como:
          - None              → sin filtro
          - dict              → se traduce a Filter (compatibilidad con callers legacy)
          - qdrant Filter     → se usa directamente (construido por QueryAdapter)

        Retorna siempre en formato estándar: list[{"id", "text", "metadata"}].
        """
        hits = self.client.search(
            collection_name=self.collection_name,
            query_vector=embedding,
            query_filter=self._resolve_filter(where),
            limit=n_results,
            with_payload=True,
        )
        return [
            {
                "id":   hit.payload.get("doc_id", str(hit.id)),
                "text": hit.payload.get("text", ""),
                "metadata": {
                    k: v for k, v in hit.payload.items()
                    if k not in ("doc_id", "text")
                },
            }
            for hit in hits
        ]


# ============================================================
# Router público  —  mantiene el nombre "ChromaAdapter"
# para no romper los imports existentes.
# ============================================================
class ChromaAdapter:
    """
    Adaptador RAG híbrido (ChromaDB / Qdrant Cloud).
    La variable VECTOR_DB_TYPE se evalúa en caliente en cada instancia,
    por lo que cambiar el entorno no requiere reiniciar el proceso completo.
    """

    def __init__(self, collection_name: str = "hellen_rag"):
        db_type = os.getenv("VECTOR_DB_TYPE", "chromadb").strip().lower()
        print(f"🔀 VectorAdapter → backend activo: [{db_type}]", flush=True)

        if db_type == "qdrant":
            self._backend = _QdrantBackend(collection_name)
        else:
            self._backend = _ChromaBackend(collection_name)

    def add_document(self, doc_id: str, text: str, embedding: list, metadata: dict = None):
        self._backend.add_document(doc_id, text, embedding, metadata)

    def query(self, embedding: list, n_results: int = 3, where: dict = None) -> list:
        return self._backend.query(embedding, n_results, where)

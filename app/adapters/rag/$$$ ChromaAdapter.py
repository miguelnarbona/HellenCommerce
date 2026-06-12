# adapters/rag/ChromaAdapter.py
#from chromadb import Client

from chromadb import HttpClient
from chromadb.config import Settings
import config


class ChromaAdapter:
    """
    Adaptador RAG para ChromaDB usando la API REST v2.
    Totalmente compatible con ChromaDB 0.5.3.
    """

    def __init__(self, collection_name="hellen_rag"):

        # Host y puerto desde tu configuración
        host = config.settings.Config.CHROMA_HOST
        port = config.settings.Config.CHROMA_PORT

        # Cliente REST moderno (API v2)
        self.client = HttpClient(
            host=host,
            port=port
        )
        
        #self.client = Client(Settings(
        #    chroma_api_impl="rest",
        #    chroma_server_host=host,
        #    chroma_server_http_port=port,
        #))

        # Crear o recuperar colección remota
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None
        )

    # ---------------------------------------------------------
    # Insertar documentos
    # ---------------------------------------------------------
    def add_document(self, doc_id: str, text: str, embedding: list, metadata: dict = None):
        if not doc_id:
            raise ValueError("doc_id no puede estar vacío.")
        if not isinstance(embedding, list):
            raise TypeError("embedding debe ser una lista de floats.")

        self.collection.add(
            ids=[doc_id],
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata or {}]
        )

    # ---------------------------------------------------------
    # Búsqueda por similitud
    # ---------------------------------------------------------
    def query(self, embedding: list, n_results: int = 3, where: dict = None):
        if not isinstance(embedding, list):
            raise TypeError("embedding debe ser una lista de floats.")

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        ids = results.get("ids", [[]])[0]

        return [
            {
                "id": ids[i],
                "text": docs[i],
                "metadata": metas[i]
            }
            for i in range(len(docs))
        ]

    # ---------------------------------------------------------
    # Compatibilidad (REST no usa persist)
    # ---------------------------------------------------------
    def persist(self):
        pass

    # ---------------------------------------------------------
    # Utilidades
    # ---------------------------------------------------------
    def count(self):
        return self.collection.count()

    def get_by_id(self, doc_id: str):
        result = self.collection.get(ids=[doc_id])
        if not result["ids"]:
            return None

        return {
            "id": result["ids"][0],
            "text": result["documents"][0],
            "metadata": result["metadatas"][0]
        }

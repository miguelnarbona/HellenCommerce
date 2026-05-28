import os
import platform
from chromadb import Client
from chromadb.config import Settings

class ChromaAdapter:
    """
    Adaptador RAG para ChromaDB usando la API REST v2.
    Compatible con ChromaDB 0.5.3.
    """

    def __init__(self, collection_name="hellen_rag"):

        system = platform.system()

        # --- Selección automática según OS ---
        if system == "Windows":
            # Modo desarrollo local
            chroma_url = os.getenv("CHROMA_URL", "http://127.0.0.1:8000")
        else:
            # Modo Docker/Linux
            chroma_url = os.getenv("CHROMA_URL", "http://chromadb_service:8000")

        # Parseo limpio del host y puerto
        host = chroma_url.split("://")[1].split(":")[0]
        port = int(chroma_url.split(":")[-1])

        # Cliente REST correcto
        self.client = Client(
            Settings(
                chroma_api_impl="rest",
                chroma_server_host=host,
                chroma_server_http_port=port,
            )
        )

        # Crear o recuperar colección
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None
        )

    def add_document(self, doc_id, text, embedding, metadata=None):
        self.collection.add(
            ids=[doc_id],
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata or {}]
        )

    def query(self, embedding, n_results=3, where=None):
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

import os
import platform
from chromadb import HttpClient

class ChromaAdapter:
    """
    Adaptador RAG para ChromaDB usando la API REST v1 (HttpClient).
    Compatible con ChromaDB 0.5.3.
    """

    def __init__(self, collection_name="hellen_rag"):

        system = platform.system()

        if system == "Windows":
            host = os.getenv("CHROMA_HOST", "127.0.0.1")
            port = int(os.getenv("CHROMA_PORT", 8001))
        else:
            host = os.getenv("CHROMA_HOST", "chromadb_service")
            port = int(os.getenv("CHROMA_PORT", 8001))

        print("=== CHROMA DEBUG ===")
        print("CHROMA FILE:", __file__)
        print("OS:", system)
        print("HOST:", host)
        print("PORT:", port)
        print("====================")

        self.client = HttpClient(
            host=host,
            port=port
        )

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

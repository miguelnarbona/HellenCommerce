# adapters/rag/QueryAdapter.py

import re
import numpy as np

class QueryAdapter:
    """
    Capa intermedia para búsqueda semántica entre usuarios.
    - Filtra por tipo contrario (comprador ↔ vendedor)
    - Re-rankea localmente por similitud coseno
    - Controla relevancia mínima
    - Limpia ruido
    """

    def __init__(self, rag, embedder, min_similarity=0.35):
        self.rag = rag
        self.embedder = embedder
        self.min_similarity = min_similarity

    # ---------------------------------------------------------
    # Similaridad coseno
    # ---------------------------------------------------------
    def _cosine(self, a, b):
        a = np.array(a)
        b = np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    # ---------------------------------------------------------
    # Query principal
    # ---------------------------------------------------------
    def query(self, tipo_usuario: str, mercancia: str, top_k: int = 5):
        """
        Recupera coincidencias semánticas entre usuarios:
        - tipo_usuario: "comprador" o "vendedor"
        - mercancia: texto de búsqueda
        """

        if not mercancia or mercancia.strip() == "":
            return []

        # Tipo contrario
        opposite = "vendedor" if tipo_usuario == "comprador" else "comprador"

        # Embedding de consulta
        query_emb = self.embedder.embed(mercancia)

        # Query cruda a Chroma
        # raw = self.rag.query(query_emb, n_results=30, where={"tipo": opposite}
        filtered = self.rag.query(query_emb, n_results=30, where={"tipo": opposite})

        # Filtrar por tipo contrario
        #filtered = [
        #    r for r in raw
        #    if r["metadata"].get("tipo") == opposite
        #]

        if not filtered:
            return []

        # Re-ranking local
        rescored = []
        for r in filtered:
            score = self._cosine(query_emb, self.embedder.embed(r["text"]))
            rescored.append((score, r))

        # Ordenar por similitud
        rescored.sort(key=lambda x: x[0], reverse=True)

        # Aplicar umbral mínimo
        rescored = [r for r in rescored if r[0] >= self.min_similarity]

        # Limitar a top_k
        rescored = rescored[:top_k]

        # Devolver solo documentos
        return [r[1] for r in rescored]
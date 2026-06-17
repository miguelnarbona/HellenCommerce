"""
HellenCommerce - QueryAdapter
Capa de búsqueda semántica con compatibilidad dual explícita:
  ChromaDB → where: dict Python estándar
  Qdrant   → Filter: objeto nativo qdrant_client.models.Filter

QueryAdapter construye el filtro nativo de cada backend directamente
mediante _build_filter(), sin delegar la traducción al VectorAdapter.
El VectorAdapter (ChromaAdapter) también acepta objetos Filter pre-construidos
como capa de seguridad defensiva.

Métodos públicos (firmas sin cambios):
  query(tipo_usuario, mercancia, top_k)   → list[dict]  [business-matching]
  query_context(user_id, text, top_k)     → list[dict]  [RAG conversacional]
"""

import os
import numpy as np


# ---------------------------------------------------------------------------
# Helpers de construcción de filtros (funciones de módulo, sin estado)
# ---------------------------------------------------------------------------

def _is_qdrant() -> bool:
    """Devuelve True si el backend vectorial activo es Qdrant."""
    return os.getenv("VECTOR_DB_TYPE", "chromadb").strip().lower() == "qdrant"


def _build_filter(conditions: dict):
    """
    Construye el objeto de filtro nativo del backend activo.

    Args:
        conditions: dict de pares clave-valor a filtrar.
                    Ejemplo: {"tipo": "vendedor"} o {"user_id": "abc123"}

    Returns:
        - ChromaDB: el mismo dict (la API de ChromaDB lo consume directamente).
        - Qdrant:   un objeto Filter con FieldCondition+MatchValue por cada par.
                    Ejemplo resultado:
                      Filter(must=[
                          FieldCondition(key="tipo", match=MatchValue(value="vendedor"))
                      ])

    Diseño:
        La función es idempotente: si conditions está vacío retorna None,
        evitando filtros vacíos que pueden fallar en ChromaDB.
    """
    if not conditions:
        return None

    if not _is_qdrant():
        # ChromaDB: dict nativo, sin transformación
        return conditions

    # Qdrant: construir Filter con un FieldCondition por cada condición
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    must = [
        FieldCondition(key=k, match=MatchValue(value=v))
        for k, v in conditions.items()
    ]
    return Filter(must=must)


# ---------------------------------------------------------------------------
# QueryAdapter
# ---------------------------------------------------------------------------

class QueryAdapter:
    """
    Capa intermedia para búsqueda semántica.

    Compatibilidad dual explícita:
      - Evalúa VECTOR_DB_TYPE en cada llamada a _build_filter().
      - Pasa el filtro en formato nativo al backend: dict para ChromaDB,
        Filter para Qdrant. Sin intermediarios ni traducciones implícitas.

    Funcionalidades:
      - Business-matching: filtra por tipo contrario (comprador ↔ vendedor).
      - RAG conversacional: filtro estricto por user_id (aislamiento de datos).
      - Re-ranking local por similitud coseno.
      - Umbral mínimo de relevancia configurable.
    """

    def __init__(self, rag, embedder, min_similarity: float = 0.35):
        self.rag            = rag
        self.embedder       = embedder
        self.min_similarity = min_similarity

    # ----------------------------------------------------------
    # Utilidades internas
    # ----------------------------------------------------------

    def _cosine(self, a, b) -> float:
        """Similitud coseno entre dos vectores."""
        a, b  = np.array(a), np.array(b)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        return float(np.dot(a, b) / denom) if denom > 0 else 0.0

    def _rerank(self, query_emb: list, raw: list, top_k: int) -> list:
        """Re-rankea resultados por similitud coseno y aplica umbral mínimo."""
        rescored = [
            (self._cosine(query_emb, self.embedder.embed(r["text"])), r)
            for r in raw
        ]
        rescored.sort(key=lambda x: x[0], reverse=True)
        return [r for score, r in rescored if score >= self.min_similarity][:top_k]

    # ----------------------------------------------------------
    # Query business-matching (firma original sin cambios)
    # ----------------------------------------------------------

    def query(self, tipo_usuario: str, mercancia: str, top_k: int = 5) -> list:
        """
        Recupera coincidencias semánticas entre compradores y vendedores.

        Construye el filtro {"tipo": opposite} en el formato nativo del backend:
          - ChromaDB: where={"tipo": "vendedor"}   (dict)
          - Qdrant:   Filter(must=[FieldCondition("tipo", MatchValue("vendedor"))])

        Args:
            tipo_usuario: "comprador" o "vendedor"
            mercancia:    Texto del producto o servicio a buscar
            top_k:        Máximo de resultados a retornar

        Returns:
            list[dict]  →  [{"id": str, "text": str, "metadata": dict}]
        """
        if not mercancia or not mercancia.strip():
            return []

        opposite  = "vendedor" if tipo_usuario == "comprador" else "comprador"
        query_emb = self.embedder.embed(mercancia)

        # Filtro nativo del backend activo
        where = _build_filter({"tipo": opposite})

        raw = self.rag.query(query_emb, n_results=30, where=where)
        if not raw:
            return []

        return self._rerank(query_emb, raw, top_k)

    # ----------------------------------------------------------
    # Query RAG conversacional con aislamiento estricto por user_id
    # ----------------------------------------------------------

    def query_context(self, user_id: str, text: str, top_k: int = 5) -> list:
        """
        Recupera recuerdos conversacionales del usuario específico.

        Aplica filtro ESTRICTO por user_id en el formato nativo del backend:
          - ChromaDB: where={"user_id": user_id}   (dict)
          - Qdrant:   Filter(must=[FieldCondition("user_id", MatchValue(user_id))])

        Garantía de aislamiento: un cliente de la tienda jamás puede leer
        el contexto conversacional de otro, independientemente del backend activo.

        Args:
            user_id: Identificador único del usuario
            text:    Texto de consulta para búsqueda semántica
            top_k:   Máximo de recuerdos a retornar

        Returns:
            list[dict]  →  [{"id": str, "text": str, "metadata": dict}]
            Formato idéntico al de ChromaDB para consumo transparente por el RAG.
        """
        if not text or not text.strip():
            return []

        query_emb = self.embedder.embed(text)

        # Filtro nativo del backend activo (con aislamiento por user_id)
        where = _build_filter({"user_id": user_id})

        raw = self.rag.query(query_emb, n_results=top_k * 2, where=where)
        if not raw:
            return []

        return self._rerank(query_emb, raw, top_k)
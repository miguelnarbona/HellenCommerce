"""
HellenCommerce - ContextManager
Administra historial conversacional limpio.

Cambios en esta versión (solo Paso 6 — vector layer):
  - _index_interaction_rag: metadata enriquecido con campo 'intents' opcional.
  - build_prompt_context: query RAG con filtro where={"user_id"} para aislamiento
    de datos (idéntico en ChromaDB y Qdrant gracias al VectorAdapter).
  - SQLite: sin cambios.
  - Firmas públicas: sin cambios.
"""

import json
import time
import re


class ContextManager:
    """
    Administra historial conversacional limpio.
    NO guarda vendedores, teléfonos, mercancías ni JSON.
    Compatible con persistencia inteligente.
    """

    def __init__(self, db, max_lines=5, rag=None, embedder=None, query_adapter=None):
        self.db            = db
        self.max_lines     = max_lines
        self.rag           = rag
        self.embedder      = embedder
        self.query_adapter = query_adapter

        # COPILOT-add: Add field to track last search results for context preservation
        # This allows CONTACTO intent to access sellers from previous COMPRA/VENTA searches
        self.last_search_results = {}

    # ---------------------------------------------------------
    # Cargar historial + current_product_query
    # ---------------------------------------------------------
    def load_context(self, user_id: str):
        conn = self.db._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT contexto, current_product_query FROM usuarios WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        if not row:
            return [], None

        raw_context          = row[0] or ""
        current_product_query = row[1] or None

        lines = raw_context.split("\n") if raw_context else []
        lines = self._sanitize_context(lines)

        return lines[-self.max_lines:], current_product_query

    # ---------------------------------------------------------
    # Guardar historial + current_product_query
    # ---------------------------------------------------------
    def save_context(
        self,
        user_id: str,
        user_msg: str | None = None,
        ai_msg: str | None = None,
        current_product_query: str | None = None,
        tipo: str = "comprador",
        **kwargs,
    ):
        # Recuperar historial previo
        conn = self.db._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT contexto, current_product_query FROM usuarios WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        prev_lines                = row[0].split("\n") if (row and row[0]) else []
        prev_current_product_query = row[1] if (row and row[1]) else None

        # Backwards-compatibility: aceptar aliases que algunas partes
        # del sistema (p.ej. Orchestrator) usan: 'message' -> user_msg,
        # 'response' -> ai_msg, y 'conversation_id' -> current_product_query.
        if user_msg is None:
            user_msg = kwargs.get('user_msg') or kwargs.get('message') or kwargs.get('msg') or ''
        if ai_msg is None:
            ai_msg = kwargs.get('ai_msg') or kwargs.get('response') or kwargs.get('reply') or ''
        if current_product_query is None:
            # Orchestrator may pass conversation_id; preserve mapping for compatibility
            current_product_query = kwargs.get('current_product_query', None) or kwargs.get('conversation_id', None)

        # COPILOT-Change:
        # Mantener el current_product_query previo cuando no se suministra uno nuevo.
        if current_product_query is None:
            current_product_query = prev_current_product_query

        # Añadir nuevas líneas
        new_lines = prev_lines + [user_msg, ai_msg]

        # COPILOT-Change:
        # Apply conditional sanitization to preserve seller context when needed
        preserve  = bool(self.last_search_results.get(user_id)) if hasattr(self, "last_search_results") else False
        new_lines = self._sanitize_context(new_lines, preserve_seller_info=preserve)

        # Limitar historial
        limited_context = "\n".join(new_lines[-self.max_lines:])

        # Guardar en SQLite: actualizar o insertar si el usuario no existe
        conn = self.db._get_conn()
        try:
            cursor = conn.cursor()
            if row:
                cursor.execute(
                    """
                    UPDATE usuarios
                    SET contexto = ?, current_product_query = ?, tipo = ?
                    WHERE user_id = ?
                    """,
                    (limited_context, current_product_query, tipo, user_id),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO usuarios (user_id, contexto, current_product_query, tipo)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, limited_context, current_product_query, tipo),
                )
            conn.commit()
        finally:
            conn.close()

        # Indexación en RAG vectorial
        self._index_interaction_rag(user_id, user_msg, ai_msg)

    # ---------------------------------------------------------
    # Sanitización del contexto
    # ---------------------------------------------------------
    # COPILOT-Change:
    # Modified to support conditional preservation of seller context
    def _sanitize_context(self, lines, preserve_seller_info=False):
        clean = []
        for line in lines:
            if not isinstance(line, str):
                continue

            l = line.strip()

            # Eliminar JSON o estructuras
            if "{" in l or "}" in l or "[" in l or "]" in l:
                continue

            # COPILOT-Change:
            # Conditionally strip seller data based on context preservation flag
            if not preserve_seller_info:
                if any(x in l.lower() for x in [
                    "nombre:", "precio:", "telefono:", "teléfono:",
                    "ubicacion:", "mercancia:", "tamaños:", "domicilio:",
                ]):
                    continue

            # Eliminar líneas muy cortas
            if len(l) < 4:
                continue

            clean.append(l)

        return clean

    # ---------------------------------------------------------
    # Indexación automática en RAG  [Paso 6 — vector layer]
    # ---------------------------------------------------------
    def _index_interaction_rag(
        self,
        user_id: str,
        user_msg: str,
        ai_msg: str,
        intents: list | None = None,      # opcional: intenciones del Paso 2
    ):
        """
        Persiste la interacción en el backend vectorial activo (ChromaDB o Qdrant).

        El metadata incluye ahora 'intents' cuando el orquestador los provee,
        enriqueciendo el payload de Qdrant para filtros futuros más precisos.
        Parámetro `intents` es opcional para mantener compatibilidad total con
        todos los callers actuales que no lo suministran.
        """
        if not (self.rag and self.embedder):
            return

        texto = (
            f"[Usuario {user_id}] "
            f"Pregunta: {user_msg} | "
            f"Respuesta IA: {ai_msg}"
        )

        try:
            embedding = self.embedder.embed(texto)
            rag       = self.rag()

            metadata = {
                "user_id": user_id,
                "tipo":    "contexto",
                "fuente":  "interaccion",
            }
            # Enriquecer con intenciones si están disponibles
            if intents:
                metadata["intents"] = ",".join(intents) if isinstance(intents, list) else str(intents)

            rag.add_document(
                doc_id=f"context_{user_id}_{int(time.time() * 1000)}",
                text=texto,
                embedding=embedding,
                metadata=metadata,
            )
        except Exception as e:
            print(f"⚠️ Error indexando en RAG vectorial: {e}", flush=True)

    # ---------------------------------------------------------
    # COPILOT-add: store / retrieve search results
    # ---------------------------------------------------------
    def store_search_results(self, user_id: str, contenido_filtrado: list, mercancia: str):
        """
        Store filtered search results for use in follow-up CONTACTO queries.
        """
        if not hasattr(self, "last_search_results") or self.last_search_results is None:
            self.last_search_results = {}

        self.last_search_results[user_id] = {
            "user_id":   user_id,
            "contenido": contenido_filtrado,
            "mercancia": mercancia,
            "timestamp": time.time(),
        }
        print(f"💾 Resultados de búsqueda guardados para {user_id}: {len(contenido_filtrado)} contactos", flush=True)

    def get_search_results(self, user_id: str) -> dict | None:
        """
        Retrieve stored search results if they belong to the current user.
        """
        if not hasattr(self, "last_search_results") or self.last_search_results is None:
            self.last_search_results = {}
            return None

        user_results = self.last_search_results.get(user_id)
        if not user_results:
            return None

        # Expirar después de 5 minutos
        if (time.time() - user_results.get("timestamp", 0)) < 300:
            return user_results

        del self.last_search_results[user_id]
        return None

    # ---------------------------------------------------------
    # Construcción de prompt enriquecido  (versión legacy)
    # ---------------------------------------------------------
    def v_1_build_prompt_context(self, user_id: str, user_msg: str):
        history, current_product_query = self.load_context(user_id)

        rag_results = []
        if self.query_adapter:
            rag_results = self.query_adapter.query(
                user_id=user_id,
                text=user_msg,
                top_k=5,
            )

        context_block = []

        if history:
            context_block.append("### Historial reciente:")
            context_block.extend(history)

        if rag_results:
            context_block.append("\n### Recuerdos relevantes:")
            for r in rag_results:
                context_block.append(f"- {r['text']}")

        context_block.append("\n### Mensaje actual del usuario:")
        context_block.append(user_msg)

        if current_product_query:
            context_block.append("\n### Consulta acumulada del usuario:")
            context_block.append(current_product_query)

        return "\n".join(context_block)

    # ---------------------------------------------------------
    # Construcción de prompt enriquecido  (activa)
    # ---------------------------------------------------------
    def build_prompt_context(self, user_id: str, user_msg: str):
        """
        Construye memoria conversacional REAL:
          - Historial limpio (SQLite)
          - Recuerdos relevantes (ChromaDB o Qdrant, con aislamiento por user_id)
          - Mensaje actual

        El filtro where={"user_id": user_id} garantiza que el RAG solo devuelva
        contexto del usuario solicitante, independientemente del backend activo.
        """

        # 1. Historial limpio desde SQLite
        history, current_product_query = self.load_context(user_id)

        # 2. Recuerdos relevantes desde el backend vectorial activo
        rag_results = []
        try:
            rag = self.rag()   # instancia de ChromaAdapter (VectorAdapter)
            emb = self.embedder.embed(user_msg)

            # Filtro obligatorio por user_id → aislamiento de datos entre clientes
            rag_docs = rag.query(emb, n_results=5, where={"user_id": user_id})

            for d in rag_docs:
                rag_results.append(d["text"])

        except Exception as e:
            print(f">>> ERROR en RAG: {e}", flush=True)

        # 3. Construcción del bloque de contexto
        context_block = []

        if history:
            context_block.append("### Historial reciente:")
            context_block.extend(history)

        if rag_results:
            context_block.append("\n### Recuerdos relevantes:")
            for r in rag_results:
                context_block.append(f"- {r}")

        context_block.append("\n### Mensaje actual del usuario:")
        context_block.append(user_msg)

        if current_product_query:
            context_block.append("\n### Consulta acumulada del usuario:")
            context_block.append(current_product_query)

        return "\n".join(context_block)

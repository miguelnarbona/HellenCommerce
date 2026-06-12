import json
import time

class ContextManager:
    """
    Administra historial conversacional y memoria semántica.
    Compatible con ChromaDB vía HTTP o local.
    Ahora usa conexión por operación (SQLiteAdapter._get_conn()).
    """

    def __init__(self, db, max_lines=5, rag=None, embedder=None, query_adapter=None):
        self.db = db
        self.max_lines = max_lines

        # Adaptadores externos
        self.rag = rag
        self.embedder = embedder
        self.query_adapter = query_adapter

    # ---------------------------------------------------------
    # Cargar historial + current_product_query
    # ---------------------------------------------------------
    def load_context(self, user_id: str):
        conn = self.db._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT contexto FROM usuarios WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
                (user_id,)
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        if not row:
            return [], None
        
        raw = row[0] or ""
        lines = raw.split("\n") if raw else []

        return lines[-self.max_lines:]
    
    def v_1_load_context(self, user_id: str):
        conn = self.db._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT contexto FROM usuarios WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
                (user_id,)
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        if not row:
            return [], None

        contexto_raw = row[0] or ""
        current_product_query = row[1] or None

        lines = contexto_raw.split("\n") if contexto_raw else []
        return lines[-self.max_lines:], current_product_query

    # ---------------------------------------------------------
    # Guardar historial + current_product_query
    # ---------------------------------------------------------
    def save_context(self, user_id: str, user_msg: str, ai_msg: str, current_product_query: str | None = None):
        # Recuperar historial previo
        conn = self.db._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT contexto FROM usuarios WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
                (user_id,)
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        lines = row[0].split("\n") if (row and row[0]) else []

        # IMPORTANTE:
        # user_msg y ai_msg YA VIENEN con "USUARIO:" y "IA:" desde IARequestBuilder
        # NO volver a agregar prefijos
        lines.extend([
            user_msg,
            ai_msg
        ])

        # Limitar historial
        limited_context = "\n".join(lines[-self.max_lines:])

        # Guardar en SQLite
        conn = self.db._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE usuarios 
                SET contexto = ?, current_product_query = ?
                WHERE user_id = ?
                """,
                (limited_context, current_product_query, user_id)
            )
            conn.commit()
        finally:
            conn.close()

        # Indexación en tiempo real en RAG
        self._index_interaction_rag(user_id, user_msg, ai_msg)

    # ---------------------------------------------------------
    # Indexación automática en RAG
    # ---------------------------------------------------------
    def _index_interaction_rag(self, user_id: str, user_msg: str, ai_msg: str):
        if not (self.rag and self.embedder):
            return

        texto = (
            f"[Usuario {user_id}] "
            f"Pregunta: {user_msg} | "
            f"Respuesta IA: {ai_msg}"
        )

        embedding = self.embedder.embed(texto)
        rag = self.rag()  # instancia nueva

        rag.add_document(
            doc_id=f"context_{user_id}_{int(time.time() * 1000)}",
            text=texto,
            embedding=embedding,
            metadata={
                "user_id": user_id,
                "tipo": "contexto",
                "fuente": "interaccion"
            }
        )

    # ---------------------------------------------------------
    # Construcción de prompt enriquecido
    # ---------------------------------------------------------
    def build_prompt_context(self, user_id: str, user_msg: str):
        history, current_product_query = self.load_context(user_id)

        # Recuperación semántica usando QueryAdapter
        rag_results = []
        if self.query_adapter:
            rag_results = self.query_adapter.query(
                user_id=user_id,
                text=user_msg,
                top_k=5
            )

        context_block = []

        # Historial reciente
        if history:
            context_block.append("### Historial reciente:")
            context_block.extend(history)

        # Recuerdos relevantes desde RAG
        if rag_results:
            context_block.append("\n### Recuerdos relevantes:")
            for r in rag_results:
                context_block.append(f"- {r['text']}")

        # Mensaje actual
        context_block.append("\n### Mensaje actual del usuario:")
        context_block.append(user_msg)

        # NUEVO: incluir mercancía acumulada
        if current_product_query:
            context_block.append("\n### Consulta acumulada del usuario:")
            context_block.append(current_product_query)

        return "\n".join(context_block)

    def load_product_state(self, user_id):
        conn = self.db._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT product_state FROM usuarios WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        if row and row[0]:
            import json
            try:
                return json.loads(row[0])
            except:
                pass  # si está corrupto, devolver estado inicial

        return {
            "producto": None,
            "modelo": None,
            "color": None,
            "ubicacion": None,
            "marca": None,
            "precio_min": None,
            "precio_max": None,
            "extras": []
        }

    def save_product_state(self, user_id, state):
        conn = self.db._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE usuarios SET product_state = ? WHERE user_id = ?",
                (json.dumps(state), user_id)
            )
            conn.commit()
        finally:
            conn.close()

# core/builder/IARequestDirector.py
import asyncio

class IARequestDirector:

    def __init__(self, builder):
        # Aqui entro la solictud del constructor al director
        self.builder = builder
        # Ya el Director tiene en la mano la socitud del Constructor

    # Aqui el Director le pasa la solicitud a la secretaria para ser procesada
    async def process_request(self, user_id, message):
        # ============================================================
        # 1. Reset + cargar usuario + mensaje
        # ============================================================

        # Director
        self.builder.reset()
        self.builder.with_user(user_id)

        # Aqui se procesa la MERCANCIA la primera vez
        self.builder.with_message(message)

        # ============================================================
        # 2. Cache
        # ============================================================
        cached = self.builder._check_cache(message)
        if cached:
            return cached

        # ============================================================
        # 3. Cargar contexto previo 
        # ============================================================
        self.builder.load_context()

        # ============================================================
        # 4. Detectar rol
        # ============================================================
        self.builder.detect_role()

        # ============================================================
        # 5. Worker detecta mercancía (NO el director)
        # ============================================================
        # Aquí NO se detecta mercancía.
        # El builder (worker) lo hará dentro de process_db() o preanalyze()
        # según tu arquitectura original.

        # ============================================================
        # 6. DB y RAG usando mercancía detectada por el worker
        # ============================================================
        await asyncio.gather(
            self.builder.process_db(),
            self.builder.process_rag()
        )

        # ============================================================
        # 7. Preanálisis (limpieza, trimming, reducción)
        # ============================================================
        self.builder.preanalyze()

        # ============================================================
        # 8. Ya el prompt no se construye aqui (Construir prompt final)
        # se construye en Mistral Service
        # ============================================================
        # self.builder.build_prompt()

        # ============================================================
        # 9. Devolver datos estructurados
        # ============================================================
        return {
            "rol": self.builder.user_role,
            "mercancia": self.builder.current_product_query,  # El worker debería actualizar detected_mercancia
            "datos_db": self.builder.db_context,
            "datos_rag": self.builder.rag_context,
            "contexto": self.builder.context,
            "memoria": self.builder.memoria
        }

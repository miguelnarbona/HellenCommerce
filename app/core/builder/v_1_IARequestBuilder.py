import asyncio
import re
import numpy as np

from app.core.cache import cache
from rapidfuzz import fuzz

class IARequestBuilder:

    def __init__(
        self,
        db,
        context_manager,
        role_detector,
        business_logic,
        prompt_builder,
        model,
        rag_factory=None,
        embedding_adapter=None
    ):
        self.db = db
        self.context_manager = context_manager
        self.role_detector = role_detector
        self.business_logic = business_logic
        self.prompt_builder = prompt_builder
        self.model = model
        self.rag_factory = rag_factory
        self.embedder = embedding_adapter
        self.rag_context = ""

        self.current_product_query = None
        self.reset()

    # ============================================================
    # RESET
    # ============================================================
    def reset(self):
        self.user_id = None
        self.message = None
        self.current_product_query = None
        self.user_role = None
        self.ai_role = None
        self.context = []
        self.db_context = {}
        self.prompt = None
        self.response = None

    # ============================================================
    # SETTERS
    # ============================================================
    def with_user(self, user_id):
        self.user_id = user_id
        return self

    def with_message(self, message):
        self.message = message

        try:
            info = self.business_logic.extractor.extract(message)
            accion = info.get("accion")
            merc = info.get("mercancia")

            if accion == "confirmacion" and not merc:
                return self

            if merc and len(merc) > 2:
                self.current_product_query = merc

        except Exception:
            pass

        return self

    # ============================================================
    # CACHE
    # ============================================================
    def _check_cache(self, msg):
        if not msg:
            return None

        try:
            for key in cache.iterkeys():
                if fuzz.ratio(msg, key) > 85:
                    return cache.get(key)
        except Exception:
            pass

        return None

    def _save_cache(self, msg, response):
        if not msg or not response:
            return
        try:
            cache.set(msg, response, expire=60 * 60 * 24)
        except Exception:
            pass

    # ============================================================
    # CONTEXT LOADING
    # ============================================================
    def load_context(self):
        ctx = self.context_manager.load_context(self.user_id)
        self.context = ctx or []
        return self

    # ============================================================
    # ROLE DETECTION
    # ============================================================
    def detect_role(self):
        query = self.current_product_query or self.message or ""
        detected = self.role_detector.detect(query)

        if detected == "seller":
            self.user_role = "vendedor"
            self.ai_role = "broker_for_buyers"
        else:
            self.user_role = "comprador"
            self.ai_role = "broker_for_sellers"

        return self

    # ============================================================
    # BUSINESS LOGIC
    # ============================================================
    async def process_db(self):

        info = self.business_logic.extractor.extract(self.message)
        accion = info.get("accion")
        merc = info.get("mercancia")

        if merc:
            query = merc
        elif accion == "confirmacion":
            query = self.current_product_query or ""
        else:
            query = ""

        # Ejecutar BusinessLogic
        self.db_context = await asyncio.to_thread(
            self.business_logic.process,
            query,
            self.user_role,
            self.user_id
        )

        # ============================================================
        # 🔥 RESTAURAR ESTADO PREVIO (vendedor anterior)
        # ============================================================
        state = self.db.get_user_state(self.user_id)

        if state and state.get("last_vendor"):

            # Si no hay vendedores nuevos, usar los previos
            if isinstance(self.db_context, dict) and not self.db_context.get("content"):
                self.db_context["content"] = state["last_vendor"]

            # Si el usuario pide explícitamente el teléfono o contacto
            if any(x in self.message.lower() for x in [
                "su número", "su telefono", "dame su", "darme su",
                "contacto", "como lo contacto", "numero del vendedor"
            ]):
                self.db_context["content"] = state["last_vendor"]

        # ============================================================
        # 🔥 GUARDAR ESTADO SI HAY VENDEDORES
        # ============================================================
        if isinstance(self.db_context, dict) and self.db_context.get("content"):
            self.db.update_user_state(
                self.user_id,
                current_product_query=self.db_context.get("mercancia"),
                product_state="esperando_detalle",
                last_vendor=self.db_context.get("content")
            )

        if isinstance(self.db_context, dict) and "respuesta" in self.db_context:
            self.response = self.db_context["respuesta"]

        return self

    # ============================================================
    # RAG
    # ============================================================
    async def process_rag(self):
        query = (self.message or "").strip()
        if not query:
            return self

        if self.rag_factory and self.embedder:
            rag = self.rag_factory()
            emb = await asyncio.to_thread(self.embedder.embed, query)
            rag_results = await asyncio.to_thread(rag.query, emb, 3)

            if rag_results:
                self.rag_context = "\n".join([r["text"] for r in rag_results])

        return self

    # ============================================================
    # PREANALYZER
    # ============================================================
    def preanalyze(self):
        self.context = self._reduce_context(self.context)
        self.context = self._sanitize_context(self.context)
        self.db_context = self._reduce_db(self.db_context)
        self.rag_context = self._reduce_rag(self.rag_context)

        self.message = self._trim_tokens(self.message, 200)
        self.rag_context = self._trim_tokens(self.rag_context, 300)

        return self

    # ============================================================
    # PROMPT BUILDER
    # ============================================================
    def build_prompt(self):
        if self.response:
            return self

        query = (self.message or "").strip()
        if not query:
            query = "Consulta del usuario"

        # ============================================================
        # 🔥 INYECTAR VENDEDORES PREVIOS SI NO HAY NUEVOS
        # ============================================================
        state = self.db.get_user_state(self.user_id)
        if state and state.get("last_vendor"):
            if isinstance(self.db_context, dict) and not self.db_context.get("content"):
                self.db_context["content"] = state["last_vendor"]

        self.prompt = (
            self.prompt_builder
                .with_roles(self.user_role, self.ai_role)
                .with_message(query)
                .with_context(self.context or [])
                .with_db_context(self.db_context or {})
                .with_rag_context(self.rag_context or "")
                .with_var("rol", self.user_role or "")
                .with_var("message", query)
                .with_var("contexto", self.context or "")
                .with_var("datos_db", self.db_context or "")
                .with_var("datos_rag", self.rag_context or "")
                .build()
        )

        self.prompt = self._trim_tokens(self.prompt, 1200)
        return self

    # ============================================================
    # CALL MISTRAL
    # ============================================================
    async def call_mistral(self, prompt):
        import httpx
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                r = await client.post(
                    "http://mistral_service:9001/infer",
                    json={"prompt": prompt, "max_tokens": 200}
                )
                data = r.json()
                return data.get("response", "")
        except Exception:
            return "Lo siento, hubo un error generando la respuesta."

    # ============================================================
    # FINAL RESPONSE
    # ============================================================
    async def get_response(self):
        # COPILOT-change: Asegurar que save_context se llame siempre para mantener coherencia
        cached = self._check_cache(self.message)
        if cached:
            self.response = cached
            self.save_context()  # COPILOT-add: Guardar incluso respuestas cacheadas
            return self.response

        if self.response:
            self.save_context()  # COPILOT-add: Garantizar guardado de respuestas directas
            return self.response

        if not self.prompt:
            return "No pude generar un prompt válido."

        respuesta = await self.call_mistral(self.prompt)
        self.response = respuesta

        self.save_context()  # COPILOT-add: Siempre guardar después de respuesta de IA
        return respuesta

    # ============================================================
    # SAVE CONTEXT
    # ============================================================
    def limpiar_respuesta_mistral(self, texto: str) -> str:
        if not texto:
            return texto

        texto = re.sub(r"^(IA:\s*)+", "", texto.strip(), flags=re.IGNORECASE)
        texto = re.sub(r"INTENCION_DETECTADA\s*:\s*\w+", "", texto, flags=re.IGNORECASE)
        texto = re.sub(r"\s{2,}", " ", texto)

        return texto.strip()

    def limpiar_linea_contexto(self, linea: str) -> str:
        if not isinstance(linea, str):
            return ""

        linea = linea.strip()

        if "[" in linea or "]" in linea:
            return ""
        if linea in ["IA:", "IA: ", "USUARIO:", "USUARIO: "]:
            return ""
        if linea.endswith(":"):
            return ""
        if "{" in linea or "}" in linea or "<" in linea or ">" in linea:
            return ""
        if len(linea) < 5:
            return ""

        return linea

    def save_context(self):
        respuesta_limpia = self.limpiar_respuesta_mistral(self.response)
        mensaje_limpio = self.limpiar_respuesta_mistral(self.message)

        clean_user_msg = f"USUARIO: {mensaje_limpio}"
        clean_ai_msg = f"IA: {respuesta_limpia}"

        self.context_manager.save_context(
            self.user_id,
            clean_user_msg,
            clean_ai_msg,
            current_product_query=self.current_product_query
        )

        self._save_cache(self.message, respuesta_limpia)
        return self

    # ============================================================
    # REDUCCIÓN
    # ============================================================
    def _reduce_context(self, ctx):
        # COPILOT-change: Aumentar límite de contexto retenido de 5 a 10 para mantener más historial
        if not ctx:
            return []
        return ctx[-10:]

    def _reduce_db(self, db):
        if not db:
            return db

        if isinstance(db, dict) and "content" in db:
            return db

        if isinstance(db, list):
            return db[:1]

        if isinstance(db, dict):
            allowed = [
                "tipo", "nombre", "mercancia", "precio",
                "ubicacion", "tamaños", "domicilio", "content", "telefono"
            ]
            return {k: v for k, v in db.items() if k in allowed}

        return db

    def _reduce_rag(self, rag):
        if not rag:
            return ""

        if isinstance(rag, list):
            rag = rag[:5]

        if isinstance(rag, str) and len(rag) > 300:
            rag = rag[:300] + "..."

        return rag

    def _sanitize_context(self, ctx):
        limpio = []
        for c in ctx:
            if not isinstance(c, str):
                continue
            if "<" in c or ">" in c:
                continue
            if "{" in c or "}" in c:
                continue
            if re.match(r"^\s*\d+\.\s*$", c):
                continue
            if len(c.strip()) < 3:
                continue
            limpio.append(c)
        return limpio

    # ============================================================
    # TOKEN TRIMMING
    # ============================================================
    def _trim_tokens(self, text, limit=800):
        if not text:
            return text

        approx_char_limit = limit * 4

        if len(text) > approx_char_limit:
            text = text[-approx_char_limit:]

        return text

import asyncio
import sqlite3
import os
import re
import numpy as np

from app.core.cache import cache
from rapidfuzz import fuzz
from math import radians, sin, cos, sqrt, atan2


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

            # Confirmación no debe borrar mercancía previa
            if accion == "confirmacion" and not merc:
                return self

            # Guardar mercancía detectada
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
        mem = self.context_manager.build_prompt_context(self.user_id, self.message)
        
        self.context = ctx or []
        self.memoria = mem or []
        return self

    # ============================================================
    # ROLE DETECTION
    # ============================================================
    def detect_role(self):
        # query = self.current_product_query or self.message or ""
        query = self.message or self.current_product_query or ""
        detected = self.role_detector.detect(query)

        if detected == "seller":
            self.user_role = "vendedor"
            self.ai_role = "broker_for_buyers"
        else:
            self.user_role = "comprador"
            self.ai_role = "broker_for_sellers"

        return self

    # ============================================================
    # BUSINESS LOGIC + PERSISTENCIA
    # ============================================================
    async def process_db(self):
        # AQUI se procesa la mercancia por segunda vez
        #info = self.business_logic.extractor.extract(self.message)
        # accion = info.get("accion")
        # merc = info.get("mercancia")
        accion = None
        merc = self.current_product_query

        # Determinar query (versión corregida)
        if self.current_product_query:
            # ✔ Usar SIEMPRE la mercancía detectada en with_message()
            query = self.current_product_query

        elif merc:
            # ✔ Si extractor detectó algo nuevo aquí, usarlo
            query = merc

        elif accion == "confirmacion":
            # ✔ Confirmación usa la mercancía previa
            query = self.current_product_query or ""

        else:
            query = ""

    #    info = self.business_logic.extractor.extract(self.message)
    #    accion = info.get("accion")
    #    merc = info.get("mercancia")

        # Determinar query
    #    if merc:
    #        query = merc
    #    elif accion == "confirmacion":
    #        query = self.current_product_query or ""
    #    else:
    #        query = ""

        # Ejecutar BusinessLogic
        self.db_context = await asyncio.to_thread(
            self.business_logic.process,
            query,                    # aquí puedes seguir pasando "cerveza fria"
            self.user_role,
            self.user_id,
            self.current_product_query   # ← mercancia ya extraída: "cerveza fria"
        )

        # ============================================================
        # 🔥 SINCRONIZAR MERCANCÍA REAL USADA POR BUSINESSLOGIC
        # ============================================================
        if isinstance(self.db_context, dict):
            merc_real = self.db_context.get("mercancia")
            if merc_real:
                self.current_product_query = merc_real

        # ============================================================
        # 🔥 PERSISTENCIA INTELIGENTE POR MERCANCÍA
        # ============================================================
        state = self.db.get_user_state(self.user_id)
        prev_item = state.get("current_product_query") if state else None

        # ------------------------------------------------------------
        # A) Si la mercancía cambió → resetear vendedor previo
        # ------------------------------------------------------------
        if prev_item and merc and merc != prev_item:
            self.db.update_user_state(
                self.user_id,
                current_product_query=merc,
                product_state="esperando_detalle",
                last_vendor=None
            )

        # ------------------------------------------------------------
        # B) Si la mercancía NO cambió → restaurar vendedor previo
        # ------------------------------------------------------------
        if state and state.get("last_vendor") and merc == prev_item:
            if isinstance(self.db_context, dict) and not self.db_context.get("content"):
                self.db_context["content"] = state["last_vendor"]

        # ------------------------------------------------------------
        # C) Si el usuario pide detalles → usar vendedor previo
        # ------------------------------------------------------------
        if any(x in self.message.lower() for x in [
            "su número", "su telefono", "dame su", "darme su",
            "contacto", "como lo contacto", "numero del vendedor"
        ]):
            if state and state.get("last_vendor"):
                self.db_context["content"] = state["last_vendor"]

        # ------------------------------------------------------------
        # D) Si BusinessLogic encontró vendedores → persistirlos
        # ------------------------------------------------------------
        if isinstance(self.db_context, dict) and self.db_context.get("content"):
            self.db.update_user_state(
                self.user_id,
                current_product_query=self.db_context.get("mercancia"),
                product_state="esperando_detalle",
                last_vendor=self.db_context.get("content")
            )

        # Si BusinessLogic devolvió respuesta directa
        if isinstance(self.db_context, dict) and "respuesta" in self.db_context:
            self.response = self.db_context["respuesta"]
        
        else:
            self.response = self.db_context["content"]
        
        # En este pedazo de codigo de process_db()  self.db_context["content"]
        # tiene mas de 3 registros escoja los 3 mas cercanos a mi ubucacion actual, evitando asi
        # el colapso de mi modelo Mistral por excederse en tiempo

        # ============================================================
        # 🔥 LIMITAR A LOS 3 MÁS CERCANOS SEGÚN UBICACIÓN REAL DEL USUARIO
        # ============================================================
        ordenados = filtrar_tres_mas_cercanos(self.response, user_id="default_user")
        self.db_context["content"] = ordenados[:3]
        self.response = self.db_context["content"]

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
    # def build_prompt(self):
    #    if self.response:
    #        return self

    #    query = (self.message or "").strip()
    #    if not query:
    #        query = "Consulta del usuario"

        # ============================================================
        # 🔥 INYECTAR VENDEDORES PREVIOS SI NO HAY NUEVOS
        # ============================================================
    #    state = self.db.get_user_state(self.user_id)
    #    if state and state.get("last_vendor"):
    #        if isinstance(self.db_context, dict) and not self.db_context.get("content"):
    #            self.db_context["content"] = state["last_vendor"]

    #    self.prompt = (
    #        self.prompt_builder
    #            .with_roles(self.user_role, self.ai_role)
    #            .with_message(query)
    #            .with_context(self.context or [])
    #           .with_db_context(self.db_context or {})
    #            .with_rag_context(self.rag_context or "")
    #            .with_var("rol", self.user_role or "")
    #            .with_var("message", query)
    #            .with_var("contexto", self.context or "")
    #            .with_var("datos_db", self.db_context or "")
    #            .with_var("datos_rag", self.rag_context or "")
    #            .with_var("memoria", self.context_manager or "")
    #            .build()
    #    )

    #    self.prompt = self._trim_tokens(self.prompt, 1200)
    #    return self

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
            current_product_query=self.current_product_query,
            tipo=self.user_role
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
    
def filtrar_tres_mas_cercanos(content: list, user_id: str):
    if not isinstance(content, list) or len(content) <= 3:
        return content
    
    COORDENADAS_PROVINCIAS = {
        "Pinar del Río": (22.4173, -83.6987),
        "Artemisa": (22.8133, -82.7619),
        "La Habana": (23.1136, -82.3666),
        "Mayabeque": (22.9870, -82.1511),
        "Matanzas": (23.0450, -81.5800),
        "Cienfuegos": (22.1460, -80.4350),
        "Villa Clara": (22.4930, -79.9660),
        "Sancti Spíritus": (21.9300, -79.4420),
        "Ciego de Ávila": (21.8400, -78.7610),
        "Camagüey": (21.3808, -77.9169),
        "Las Tunas": (20.9600, -76.9540),
        "Holguín": (20.8872, -76.2631),
        "Granma": (20.3833, -76.6413),
        "Santiago de Cuba": (20.0200, -75.8290),
        "Guantánamo": (20.1440, -75.2090),
        "Isla de la Juventud": (21.8833, -82.8000)
    }

    # Conexión segura para este hilo
    conn = sqlite3.connect(
        os.getenv("SQLITE_PATH"),
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ubicación REAL del usuario
    cur.execute("""
        SELECT lat, lon
        FROM usuarios
        WHERE user_id = ?
        LIMIT 1
    """, (user_id,))

    row = cur.fetchone()
    conn.close()

    if not row or row["lat"] is None or row["lon"] is None:
        return content[:3]

    lat_u = row["lat"]
    lon_u = row["lon"]

    # Haversine
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    def distancia(v):
        lat_v = v.get("lat")
        lon_v = v.get("lon")

        # Si no tiene coordenadas → usar provincia
        if lat_v is None or lon_v is None:
            prov = v.get("ubicacion")
            if prov in COORDENADAS_PROVINCIAS:
                lat_v, lon_v = COORDENADAS_PROVINCIAS[prov]
            else:
                return float("inf")

        return haversine(lat_u, lon_u, lat_v, lon_v)

    ordenados = sorted(content, key=distancia)
    return ordenados[:3]
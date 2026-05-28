import re
import json

class BusinessLogic:
    """
    Orquesta el flujo principal:
    1. Extrae información del mensaje (solo si no viene dada).
    2. Normaliza la mercancía/negocio/servicio/categoría.
    3. Busca coincidencias exactas en SQLite.
    4. Busca coincidencias semánticas vía QueryAdapter.
    5. Registra al usuario si no hay coincidencias.
    6. Guarda estado de continuidad.
    """

    def __init__(self, db, extractor, rag_factory=None, embedder=None, query_adapter=None, mqtt=None, map_logic=None):
        self.db = db
        self.extractor = extractor
        self.rag_factory = rag_factory
        self.embedder = embedder
        self.query_adapter = query_adapter
        self.mqtt = mqtt
        self.map_logic = map_logic

    # ============================================================
    #  NORMALIZACIÓN GENÉRICA DEL NÚCLEO
    # ============================================================
    def _extraer_nucleo_generico(self, frase: str):
        frase = frase.lower().strip()
        tokens = frase.split()

        STOPWORDS = {
            "una","un","uno","unas","unos",
            "alguna","algun","algunos","algunas",
            "la","el","las","los",
            "mi","tu","su","sus",
            "esta","este","ese","esa",
            "muy","bien","mal",
            "por","para","de","del","al",
            "fria","frio","helada","helado",
            "fresco","fresca","nuevo","nueva",
            "barato","barata","caro","cara",
            "pequeño","pequeña","grande",
            "importado","importada","cubano","cubana"
        }

        modelos = [t for t in tokens if any(c.isdigit() for c in t)]

        nucleo = None
        for t in tokens:
            if t not in STOPWORDS and len(t) > 1 and not t.isdigit():
                nucleo = t
                break

        if not nucleo:
            nucleo = frase

        if modelos:
            return nucleo + " " + " ".join(modelos)

        return nucleo

    # ============================================================
    #  PROCESAR MENSAJE PRINCIPAL
    # ============================================================
    def process(self, message: str, role: str, user_id: str, mercancia: str | None = None):
        """
        Punto central de entrada.
        """

        # ------------------------------------------------------------
        # 1) EXTRAER INFORMACIÓN SOLO SI NO VIENE DADA
        # ------------------------------------------------------------
        if mercancia is None:
            info = self.extractor.extract(message)

            merc = info.get("mercancia")
            negocio = info.get("negocio")
            servicio = info.get("servicio")
            categoria = info.get("categoria")
        else:
            # Si viene mercancia desde el builder, respetarla
            merc = mercancia
            negocio = None
            servicio = None
            categoria = None

        # ------------------------------------------------------------
        # 2) DETERMINAR EL ITEM PRINCIPAL
        # ------------------------------------------------------------
        # Prioridad:
        # 1) mercancia
        # 2) negocio
        # 3) servicio
        # 4) categoria
        valor = merc or negocio or servicio or categoria

        if valor:
            item = self._extraer_nucleo_generico(valor)
        else:
            item = "desconocido"

        # ------------------------------------------------------------
        # 3) BÚSQUEDA EXACTA EN SQLITE
        # ------------------------------------------------------------
        tipo = "vendedor" if role == "comprador" else "comprador"
        exactos = self._buscar_exactos(tipo, item)

        if exactos:
            self.db.update_user_state(
                user_id,
                current_product_query=item,
                product_state="esperando_detalle",
                last_vendor=exactos
            )
            return {
                "status": "ok",
                "role": tipo,
                "mercancia": item,
                "content": exactos,
                "fuente": "db"
            }

        # ------------------------------------------------------------
        # 4) BÚSQUEDA SEMÁNTICA
        # ------------------------------------------------------------
        if self.query_adapter:
            sem = self._buscar_semanticos(tipo, item)
            if sem:
                self.db.update_user_state(
                    user_id,
                    current_product_query=item,
                    product_state="esperando_detalle",
                    last_vendor=sem
                )
                return {
                    "status": "ok",
                    "role": tipo,
                    "mercancia": item,
                    "content": sem,
                    "fuente": "semantic"
                }

        # ------------------------------------------------------------
        # 5) REGISTRAR USUARIO (si la mercancía es válida)
        # ------------------------------------------------------------
        if item != "desconocido":
            self.db.registrar_usuario({
                "user_id": user_id,
                "tipo": role,
                "mercancia": item,
                "estado": "activo",
                "current_product_query": item
            })

            self.db.update_user_state(
                user_id,
                current_product_query=item,
                product_state="sin_vendedores",
                last_vendor=[]
            )

            return {
                "status": "ok",
                "role": role,
                "mercancia": item,
                "content": [],
                "fuente": "registro"
            }

        # ------------------------------------------------------------
        # 6) SIN MERCANCÍA
        # ------------------------------------------------------------
        return {
            "status": "ok",
            "role": role,
            "mercancia": "desconocido",
            "content": [],
            "fuente": "sin_mercancia"
        }

    # ============================================================
    #  BÚSQUEDA EXACTA
    # ============================================================
    def _buscar_exactos(self, tipo, item):
        return self.db.buscar_coincidencias(tipo, item)

    # ============================================================
    #  BÚSQUEDA SEMÁNTICA
    # ============================================================
    def _buscar_semanticos(self, tipo, item):
        try:
            return self.query_adapter.query(tipo, item) or []
        except Exception:
            return []

    # ============================================================
    #  ENTREGA DE DATOS PREVIOS
    # ============================================================
    def _entregar_datos_previos(self, user_id: str):
        state = self.db.get_user_state(user_id)
        if not state:
            return self._respuesta_vacia("comprador", None)

        last_vendor = state.get("last_vendor")
        merc = state.get("current_product_query")

        if not last_vendor:
            return self._respuesta_vacia("comprador", merc)

        return {
            "status": "ok",
            "role": "comprador",
            "mercancia": merc,
            "content": last_vendor
        }

    # ============================================================
    #  FORMATEAR FICHA
    # ============================================================
    def _formatear_ficha(self, vendedor: dict, rol: str):
        return {
            "id": vendedor.get("id"),
            "tipo": rol,
            "nombre": vendedor.get("nombre"),
            "mercancia": vendedor.get("mercancia"),
            "precio": vendedor.get("precio"),
            "ubicacion": vendedor.get("ubicacion"),
            "tamaños": vendedor.get("tamaños") or "",
            "domicilio": vendedor.get("domicilio", 0),
            "telefono": vendedor.get("telefono")
        }

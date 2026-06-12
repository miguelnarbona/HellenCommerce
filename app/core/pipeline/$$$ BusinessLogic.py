class BusinessLogic:
    """
    Orquesta el flujo principal:
    1. Extrae información del mensaje.
    2. Busca coincidencias directas en SQLite.
    3. Busca coincidencias semánticas vía QueryAdapter.
    4. Registra al usuario si no hay coincidencias.
    5. Busca emparejamientos cruzados.
    6. Indexa en RAG para memoria semántica.
    """

    def __init__(self, db, extractor, rag_factory=None, embedder=None, query_adapter_factory=None, mqtt=None, map_logic=None):
        self.db = db
        self.extractor = extractor
        self.rag_factory = rag_factory
        self.embedder = embedder
        self.query_adapter_factory = query_adapter_factory
        self.mqtt = mqtt
        self.map_logic = map_logic 

    # ---------------------------------------------------------
    # MÉTODO PRINCIPAL
    # ---------------------------------------------------------
    def process(self, message: str, role: str, user_id: str):
        info = self.extractor.extract(message)

        usuario = self.db.obtener_usuario(user_id)

        if usuario:
            self.db.actualizar_usuario(user_id, {
                "nombre": info.get("nombre"),
                "telefono": info.get("telefono"),
                "correo": info.get("correo"),
                "ubicacion": info.get("ubicacion"),
                "mercancia": info.get("mercancia"),
                "tamaños": info.get("tamaños"),
                "precio": info.get("precio"),
                "domicilio": info.get("domicilio"),
            })

        # ---------------------------------------------------------
        # Aceptación de notificaciones
        # ---------------------------------------------------------
        if info.get("accion") == "aceptar_notificaciones":
            self._activar_notificaciones(user_id, info)
            return {
                "status": "ok",
                "role": role,
                "mercancia": info.get("mercancia", "desconocido"),
                "content": ["Notificaciones activadas."],
                "respuesta": "Perfecto, te avisaré cuando haya novedades.",
                "fuente": "respuesta_final"
            }

        # ---------------------------------------------------------
        # Lógica existente
        # ---------------------------------------------------------
        item = info.get("mercancia")
        if not item or not item.strip():
            item = "desconocido"

        tipo = "comprador" if role in ["comprador", "buyer"] else "vendedor"

        if info.get("accion") == "confirmacion":
            r = self._entregar_datos_previos(user_id)
            r["fuente"] = "respuesta_final"
            return r

        # 1. Búsqueda exacta
        direct = self._buscar_exactos(tipo, item)
        if direct:
            direct["fuente"] = "db"
            return direct

        # 2. Búsqueda semántica
        semantic = self._buscar_semanticos(tipo, item)
        if semantic:
            semantic["fuente"] = "semantic"
            return semantic

        # 3. Registrar usuario
        self._registrar_usuario(info, message, tipo, user_id, item)

        # 4. Emparejamiento cruzado
        cross = self._buscar_cruzado(tipo, item)
        if cross:
            cross["fuente"] = "cross"

            opposite = "vendedor" if tipo == "comprador" else "comprador"
            usuario = self.db.obtener_usuario(user_id)
            if usuario and usuario.get("acepta_notificaciones"):
                self.enviar_notificacion(
                    user_id=user_id,
                    topic=usuario["canal"],
                    mensaje=f"Encontré nuevos {opposite} de {item}."
                )
            return cross

        # 5. Guardar en RAG
        self._guardar_en_rag(info, tipo, user_id, item)

        # 6. Respuesta vacía
        vacia = self._respuesta_vacia(tipo, item, user_id)
        vacia["fuente"] = "empty"
        return vacia

    # ---------------------------------------------------------
    # Activar notificaciones
    # ---------------------------------------------------------
    def _activar_notificaciones(self, user_id: str, info: dict):
        topic = f"usuarios/{user_id}"
        preferencias = info.get("preferencias", "general")

        cursor = self.db.conn.cursor()
        cursor.execute("""
            UPDATE usuarios
            SET acepta_notificaciones = 1,
                canal = ?,
                preferencias = ?
            WHERE user_id = ?
        """, (topic, preferencias, user_id))

        self.db.conn.commit()

    # ---------------------------------------------------------
    # BÚSQUEDA EXACTA
    # ---------------------------------------------------------
    def _buscar_exactos(self, tipo: str, item: str):
        coincidencias = self.db.buscar_coincidencias(tipo, item)
        if not coincidencias:
            return None

        historial = []
        for v in coincidencias:
            historial.append({
                "id": v["id"],
                "tipo": v["tipo"],
                "mercancia": v["mercancia"],
                "precio": v["precio"],
                "ubicacion": v["ubicacion"],
                "tamaños": v.get("tamaños"),
                "domicilio": v["domicilio"]
            })

        return {
            "status": "ok",
            "role": tipo,
            "mercancia": item,
            "content": historial
        }

    # ---------------------------------------------------------
    # BÚSQUEDA SEMÁNTICA
    # ---------------------------------------------------------
    def _buscar_semanticos(self, tipo, item):
        if not self.query_adapter_factory:
            return None

        resultados = self.query_adapter_factory().query(tipo, item)
        if not resultados:
            return None

        opciones = []
        for r in resultados[:3]:
            meta = r.get("metadata", {})
            opciones.append({
                "id": meta.get("user_id"),
                "tipo": meta.get("tipo", tipo),
                "mercancia": meta.get("mercancia", item),
                "precio": meta.get("precio", "N/D"),
                "ubicacion": meta.get("ubicacion", "N/D"),
                "tamaños": meta.get("tamaños", ""),
                "telefono": meta.get("telefono"),
                "correo": meta.get("correo"),
                "domicilio": meta.get("domicilio", 0)
            })

        return {
            "status": "semantic",
            "role": tipo,
            "mercancia": item,
            "content": opciones
        }

    # ---------------------------------------------------------
    # REGISTRO EN SQLITE
    # ---------------------------------------------------------
    def _registrar_usuario(self, info, message, tipo, user_id, item):
        data = {
            "user_id": user_id,
            "tipo": tipo,
            "nombre": info.get("nombre", tipo.capitalize()),
            "mercancia": item,
            "tamaños": info.get("tamaños", ""),
            "precio": info.get("precio"),
            "ubicacion": info.get("ubicacion"),
            "telefono": info.get("telefono"),
            "correo": info.get("correo"),
            "contacto": info.get("telefono") or info.get("correo") or user_id,
            "domicilio": info.get("domicilio", 0),
            "estado": "activo",
            "contexto": f"USUARIO: {message}\nIA: Registro guardado."
        }
        self.db.registrar_usuario(data)

    # ---------------------------------------------------------
    # EMPAREJAMIENTO CRUZADO
    # ---------------------------------------------------------
    def _buscar_cruzado(self, tipo, item):
        opposite = "vendedor" if tipo == "comprador" else "comprador"
        matches = self.db.buscar_coincidencias(opposite, item)
        if not matches:
            return None

        opciones = []
        for m in matches[:3]:
            opciones.append({
                "id": m["id"],
                "tipo": m["tipo"],
                "mercancia": m["mercancia"],
                "precio": m["precio"],
                "ubicacion": m["ubicacion"],
                "tamaños": m.get("tamaños"),
                "telefono": m.get("telefono"),
                "correo": m.get("correo"),
                "domicilio": m["domicilio"]
            })

        return {
            "status": "match",
            "role": tipo,
            "mercancia": item,
            "content": opciones
        }

    # ---------------------------------------------------------
    # GUARDAR EN RAG
    # ---------------------------------------------------------
    def _guardar_en_rag(self, info, tipo, user_id, item):
        if not (self.rag_factory and self.embedder):
            return
        if item == "desconocido":
            return

        texto = (
            f"Tipo usuario: {tipo}. "
            f"Mercancía: {item}. "
            f"Precio: {info.get('precio')}. "
            f"Ubicación: {info.get('ubicacion')}."
        )
        embedding = self.embedder.embed(texto)
        rag = self.rag_factory()  # instancia nueva por request
        rag.add_document(
            doc_id=f"{tipo}_{user_id}_{item}".replace(" ", "_").lower(),
            text=texto,
            embedding=embedding,
            metadata={"user_id": user_id, "tipo": tipo, "mercancia": item}
        )

    # ---------------------------------------------------------
    # RESPUESTA VACÍA
    # ---------------------------------------------------------
    def _respuesta_vacia(self, tipo, item, user_id=None):
        opposite = "vendedor" if tipo == "comprador" else "comprador"

        pregunta_notificaciones = ""
        if user_id:
            usuario = self.db.obtener_usuario(user_id)
            if usuario and not usuario.get("acepta_notificaciones"):
                pregunta_notificaciones = (
                    f"¿Deseas recibir notificaciones cuando aparezca algún {opposite} de {item}? "
                    f"Si es así, escribe: notificame"
                )

        contenido = [f"No encontré coincidencias para {item}."]

        if pregunta_notificaciones:
            contenido.append(pregunta_notificaciones)

        return {
            "status": "empty",
            "role": tipo,
            "mercancia": item,
            "content": contenido
        }

    # ---------------------------------------------------------
    # ENTREGA DE DATOS PREVIOS
    # ---------------------------------------------------------
    def _entregar_datos_previos(self, user_id: str):
        ultimo = self.db.obtener_historial_usuario(user_id)
        if not ultimo:
            return self._respuesta_vacia("comprador", None)

        mercancia = ultimo.get("mercancia")
        if not mercancia:
            return self._respuesta_vacia("comprador", None)

        vendedores = self.db.buscar_coincidencias("vendedor", mercancia)
        if not vendedores:
            return self._respuesta_vacia("comprador", mercancia)

        v = vendedores[0]
        ficha = self._formatear_ficha(v, "vendedor")

        return {
            "status": "ok",
            "role": "comprador",
            "mercancia": mercancia,
            "content": [ficha]
        }

    # ---------------------------------------------------------
    # NOTIFICACIONES
    # ---------------------------------------------------------
    def enviar_notificacion(self, user_id: str, topic: str, mensaje: str):
        self.db.registrar_notificacion({
            "user_id": user_id,
            "tipo": topic,
            "mensaje": mensaje
        })

        if self.mqtt:
            self.mqtt.publish(topic, mensaje)

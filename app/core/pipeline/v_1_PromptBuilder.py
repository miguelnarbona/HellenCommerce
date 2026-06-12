class PromptBuilder:

    def __init__(self):
        self.user_role = None
        self.ai_role = None
        self.message = None
        self.context = []
        self.db_context = ""
        self.rag_context = ""

    def with_roles(self, user_role, ai_role):
        self.user_role = user_role
        self.ai_role = ai_role
        return self

    def with_message(self, message):
        self.message = message
        return self

    def with_context(self, context):
        self.context = context
        return self

    def with_db_context(self, db_context):
        self.db_context = db_context
        return self

    def with_rag_context(self, rag_text):
        self.rag_context = rag_text
        return self
    
    def v_1_build(self):
        historial = "\n".join(self.context[-5:]) if self.context else ""
        rag_info = self.rag_context or "Sin información adicional."

        # Si db_context es lista de dicts, conviértelo en texto legible
        if isinstance(self.db_context, list):
            db_info = "\n".join([
                f"Usuario {d.get('id')} | Tipo: {d.get('tipo')} | Mercancía: {d.get('mercancia')} | "
                f"Precio: {d.get('precio')} | Ubicación: {d.get('ubicacion')} | Tamaños: {d.get('tamaños')} | "
                f"Domicilio: {'Sí' if d.get('domicilio') else 'No'}"
                for d in self.db_context
            ])
        elif isinstance(self.db_context, dict):
            db_info = "\n".join([f"{k}: {v}" for k, v in self.db_context.items()])
        else:
            db_info = self.db_context or "Sin datos."

        prompt = f"""
            <sistema>
            Eres un BROKER INTERMEDIARIO profesional especializado en conectar compradores y vendedores.

            Tu comportamiento depende del usuario:
            - Si el usuario es COMPRADOR → actúas como GESTOR DE VENDEDORES.
            - Si el usuario es VENDEDOR → actúas como GESTOR DE COMPRADORES.

            No compras ni vendes directamente. Tu función es filtrar, negociar, conectar, evaluar precios, validar información y facilitar acuerdos reales.

            INSTRUCCIONES IMPORTANTES:
            - Usa SOLO el bloque <contexto_base> para tu respuesta.
            - NO repitas la petición del usuario ni el contenido de <contexto_rag>.
            - Redacta directamente la respuesta en lenguaje natural, clara y profesional.
            - Nunca inventes datos.
            </sistema>

            <usuario>
            {self.user_role}: {self.message}
            </usuario>

            <contexto_base>
            {db_info}
            </contexto_base>

            <historial>
            {historial}
            </historial>
            """

        return prompt.strip()

    def build(self):
        # Historial limpio
        historial = "\n".join(self.context[-5:]) if self.context else ""

        # RAG limpio
        rag_info = self.rag_context or "Sin información adicional."

        # DB context formateado: si es lista de dicts, conviértelo en texto
        if isinstance(self.db_context, list):
            db_info = "\n".join([
                f"Usuario {d.get('id')} | Tipo: {d.get('tipo')} | Mercancía: {d.get('mercancia')} | "
                f"Precio: {d.get('precio')} | Ubicación: {d.get('ubicacion')} | Tamaños: {d.get('tamaños')} | "
                f"Domicilio: {'Sí' if d.get('domicilio') else 'No'}"
                for d in self.db_context
            ])
        elif isinstance(self.db_context, dict):
            db_info = "\n".join([f"{k}: {v}" for k, v in self.db_context.items()])
        else:
            db_info = self.db_context or "Sin datos."

        # Prompt final
        v_1_prompt = f"""
            <sistema>
            Eres un BROKER INTERMEDIARIO profesional especializado en conectar compradores y vendedores.

            Tu comportamiento depende del usuario:
            - Si el usuario es COMPRADOR → actúas como GESTOR DE VENDEDORES.
            - Si el usuario es VENDEDOR → actúas como GESTOR DE COMPRADORES.

            No compras ni vendes directamente. Tu función es filtrar, negociar, conectar, evaluar precios, validar información y facilitar acuerdos reales.

            INSTRUCCIONES IMPORTANTES:
            - Usa SOLO el bloque <contexto_base> para tu respuesta.
            - NO repitas la petición del usuario ni el contenido de <contexto_rag>.
            - Redacta directamente la respuesta en lenguaje natural, clara y profesional.
            - Nunca inventes datos.

            Si el role es "{self.user_role}" debes responder SOLO usando el contexto_base, filtrado por el rol opuesto:
            - Comprador → mostrar vendedores
            - Vendedor → mostrar compradores

            Responde SIEMPRE en tono profesional, claro y orientado a cerrar operaciones reales.
            </sistema>

            <usuario>
            {self.user_role}: {self.message}
            </usuario>

            <contexto_base>
            {db_info}
            </contexto_base>

            <contexto_rag>
            {rag_info}
            </contexto_rag>

            <historial>
            {historial}
            </historial>
            """
        
        prompt = f"""
                <role>
                    Asume el ROLE de INTERMEDIARIO profesional especializado en conectar clientes compradores con clientes vendedores.
                    - Cuando el role del cliente es: {self.user_role} = COMPRADOR o BUYER te comportaras como GESTOR DE VENTAS.
                    - Cuando el role del cliente es: {self.user_role} = VENDEDOR o SELLER te comportaras como GESTOR DE COMPRAS.
                </role>
                
                <intermediacion> 
                    - Nunca ofrezcas comprar o vender mercancia directamente.
                    - Tu función es filtrar, intermediar en la negociacion, conectar, evaluar precios, asociados exclusivamente a la solicitud: {self.message} del cliente.
                    - Limitate a responder solamente con la informacion obtenida en {self.db_context["content"]} que se relaciones con {self.message}.
                    - Ajustate a responder solo lo que se te preguntan de manera profesional y organizada.
                </itermediacion>
        """
        return prompt.strip()
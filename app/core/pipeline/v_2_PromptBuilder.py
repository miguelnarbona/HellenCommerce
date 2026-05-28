class PromptBuilder:
    def __init__(self):
        self.user_role = None
        self.ai_role = None
        self.message = None
        self.context = []
        self.db_context = {}
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

    def build(self):
        status = self.db_context.get("status", "empty")
        mercancia = self.db_context.get("mercancia", "desconocido")
        content = self.db_context.get("content", [])
        fuente = self.db_context.get("fuente", "desconocida")

        datos_objetivos = {
            "status": status,
            "mercancia": mercancia,
            "fuente": fuente,
            "resultados": content
        }

        reglas = """
            <sistema>
            Redacta una respuesta profesional, clara y natural, actuando como broker.

            OBJETIVO PRINCIPAL:
            El usuario debe obtener una respuesta útil, completa y accionable en menos de 3 interacciones.

            INSTRUCCIONES:
            1. Responde de forma directa y concreta desde el primer mensaje.
            2. No pidas aclaraciones a menos que sea absolutamente necesario.
            3. No incluyas etiquetas XML (<...>) en tu respuesta.
            4. No muestres <contexto_conversacional>, <datos_db> ni <datos_rag>.
            5. No repitas el mensaje del usuario.
            6. No muestres texto técnico ni bloques de datos.
            7. Si hay datos disponibles, ofrece una recomendación clara y una acción siguiente.
            8. Si no hay datos suficientes, ofrece alternativas realistas sin inventar información.
            9. Mantén un tono profesional, cordial y orientado a resolver el problema del usuario.
            10. Responde SOLO con el texto final para el {self.user_role}.
            </sistema>
            """

        prompt = f"""
            {reglas}

            <rol_usuario>
            {self.user_role}
            </rol_usuario>

            <mensaje_usuario>
            {self.message}
            </mensaje_usuario>

            <contexto_conversacional>
            {self.context}
            </contexto_conversacional>

            <datos_db>
            {datos_objetivos}
            </datos_db>

            <datos_rag>
            {self.rag_context}
            </datos_rag>

            <tarea>
            Redacta una respuesta profesional, clara y natural, actuando como broker.
            </tarea>
            """

        return prompt.strip()

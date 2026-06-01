from pathlib import Path
import platform
import json
import re

class PromptBuilder:
    def __init__(self, template_input: str = None, variables: dict | None = None):
        """
        template_input puede ser:
        - Ruta a archivo (str o Path)
        - Texto completo del prompt
        """
        self.user_role = None
        self.ai_role = None
        self.message = None
        self.context = []
        self.db_context = {}
        self.rag_context = ""
        self.memoria = []
        self.vars = variables or {}

        # Detectar si es ruta o texto
        if isinstance(template_input, (str, Path)) and Path(str(template_input)).exists():
            self.template_path = Path(template_input)
            self.template_text = None
        else:
            self.template_path = None
            self.template_text = template_input  # TEXTO DIRECTO

        system = platform.system() 
        from app.utils.paths import hc_path
        self.ROLE_PROMPTS = {
            "comprador": hc_path("app/prompts/broker_prompt_vendedor.txt"),
            "vendedor": hc_path("app/prompts/broker_prompt_comprador.txt"),
        }

    # -----------------------------
    # Métodos de configuración
    # -----------------------------
    def with_var(self, key, value):
        self.vars[key] = value
        return self

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
    
    def with_memoria(self, memoria):
        self.memoria = memoria
        return self

    # -----------------------------
    # Compatibilidad con worker
    # -----------------------------
    def resolve_template_path(self):
        """
        SOLO se usa cuando NO se pasó texto directo.
        """
        if self.template_path:
            return self.template_path

        if self.user_role in self.ROLE_PROMPTS:
            return Path(self.ROLE_PROMPTS[self.user_role])

        raise ValueError(f"No hay prompt definido para el rol: {self.user_role}")
    
    # -----------------------------
    # Build universal (worker + FastAPI)
    # -----------------------------
    def build(self):
        # 1. Cargar plantilla
        if self.template_text is not None:
            prompt = self.template_text
        else:
            template_path = self.resolve_template_path()
            prompt = template_path.read_text(encoding="utf-8")

        # 2. Convertir diccionarios y listas a JSON legible
        safe_vars = {}
        for k, v in self.vars.items():
            if isinstance(v, (dict, list)):
                safe_vars[k] = json.dumps(v, indent=2, ensure_ascii=False)
            else:
                safe_vars[k] = v if v is not None else ""

        # 3. Garantizar claves mínimas
        default_keys = [
            "mercancia", "mercancias", "mercancia_previa",
            "message", "datos_db", "datos_rag", "contexto",
            "rol", "nombre_vendedor", "precio", "ubicacion", "domicilio"
        ]
        for key in default_keys:
            safe_vars.setdefault(key, "")

        # 4. INYECTAR DATOS FALTANTES (FIX CRÍTICO)
        # -----------------------------------------------------

        # Asegurar que datos_db SIEMPRE esté presente
        if not safe_vars.get("datos_db"):
            safe_vars["datos_db"] = json.dumps(self.db_context, indent=2, ensure_ascii=False)

        # Asegurar que contexto SIEMPRE esté presente
        if not safe_vars.get("contexto"):
            safe_vars["contexto"] = "\n".join(self.context)

        # Asegurar que datos_rag SIEMPRE esté presente
        if not safe_vars.get("datos_rag"):
            safe_vars["datos_rag"] = self.rag_context

        # Asegurar que message SIEMPRE esté presente
        if not safe_vars.get("message"):
            safe_vars["message"] = self.message or ""
        
        # Asegurar que la memoria SIEMPRE esté presente
        if not safe_vars.get("memoria"):
            safe_vars["memoria"] = self.memoria or ""

        # -----------------------------------------------------

        # 5. Formatear sin riesgo de KeyError
        try:
            return prompt.format(**safe_vars)
        except KeyError as e:
            print(f"[PromptBuilder] ⚠️ Variable faltante en el prompt: {e}")
            return prompt

    # -----------------------------
    # Build clásico (worker)
    # -----------------------------
    def v_1_build(self):
        template_path = self.resolve_template_path()
        prompt = template_path.read_text(encoding="utf-8")
        return prompt.format(**self.vars)
    

    # -----------------------------
    # Build inteligente (solo texto)
    # -----------------------------
    def v_3_build(self):
        if not self.template_text:
            raise ValueError("v_3_build solo funciona con texto directo.")

        prompt = self.template_text

        safe_vars = {}
        for k, v in self.vars.items():
            if isinstance(v, (dict, list)):
                safe_vars[k] = json.dumps(v, indent=2, ensure_ascii=False)
            else:
                safe_vars[k] = v if v is not None else ""

        vars_requeridas = re.findall(r"{(.*?)}", prompt)
        vars_finales = {key: safe_vars.get(key, "") for key in vars_requeridas}

        try:
            return prompt.format(**vars_finales)
        except Exception as e:
            print(f"[PromptBuilder] ⚠️ Error formateando prompt: {e}")
            return prompt

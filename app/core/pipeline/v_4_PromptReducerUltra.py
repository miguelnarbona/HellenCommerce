import re
import os
import platform
from pathlib import Path


class PromptReducerUltra:
    def __init__(self, content=None, contexto_previo=None, message=None, role_broker=None):
        self.content = content or []
        self.message = message or ""
        self.contexto_previo = contexto_previo or []
        self.role_broker = role_broker

        system = platform.system()
        if system == "Windows":
            self.keywords_buy = self.load_keywords(r"c:\HellenCommerce\app\resources\keywords_buy.txt")
            self.keywords_sell = self.load_keywords(r"c:\HellenCommerce\app\resources\keywords_sel.txt")
        else:
            self.keywords_buy = self.load_keywords(r"/app/resources/keywords_buy.txt")
            self.keywords_sell = self.load_keywords(r"/app/resources/keywords_sel.txt")
        
        print(f">>>>>> MESSAGE PROMPTR: {self.message} <<<<<<<<<\n", flush=True)
    
    # ---------------------------------------------------------
    # Cargar palabras clave desde archivo
    # ---------------------------------------------------------
    
    def load_keywords(self, ruta: str):
        try:
            p = Path(ruta)
            if p.exists():
                return [
                    x.strip().lower()
                    for x in p.read_text(encoding="utf-8").splitlines()
                    if x.strip()
                ]
        except Exception:
            pass
        return []

    # ---------------------------------------------------------
    # Convierte un dict en texto plano estructurado
    # ---------------------------------------------------------
    def format_item(self, item: dict) -> str:
        return "\n".join([f"  {k.capitalize()}: {v}" for k, v in item.items()])

    # ---------------------------------------------------------
    # Extrae mercancía usando keywords reales
    # ---------------------------------------------------------
    def extract_mercancia(self, mensaje: str) -> str:
        texto = mensaje.lower()
        tokens = re.findall(r"[a-záéíóúñ0-9$]+", texto)

        def es_numero_o_precio(t: str) -> bool:
            if any(s in t for s in ["$", "usd", "cup"]):
                return True
            return t.isdigit()

        # STOPWORDS = keywords + palabras comunes + placeholders genéricos
        stopwords = set(self.keywords_buy + self.keywords_sell)
        stopwords.update({
            "tengo", "tienes", "tiene", "hay",
            "quiero", "busco", "necesito",
            "vender", "vendo", "comprar", "compro",
            "disponible", "disponibles",
            "hola", "buenas", "buenos", "dias", "días",

            # placeholders genéricos
            "producto", "productos",
            "mercancia", "mercancía",
            "articulo", "artículo",
            "cosa", "cosas",
            "item", "ítem",
        })

        # 1) keywords de COMPRA
        for i, tok in enumerate(tokens):
            if tok in self.keywords_buy and i + 1 < len(tokens):
                candidato = tokens[i + 1]
                if candidato not in stopwords and not es_numero_o_precio(candidato):
                    return candidato

        # 2) keywords de VENTA
        for i, tok in enumerate(tokens):
            if tok in self.keywords_sell and i + 1 < len(tokens):
                candidato = tokens[i + 1]
                if candidato not in stopwords and not es_numero_o_precio(candidato):
                    return candidato
                
        # 3) patrón "para X"
        m = re.search(r"para\s+([a-záéíóúñ]+)", texto)
        if m:
            c = m.group(1)
            if c not in stopwords:
                return c

        # 4) Fallback: primer token válido
        for t in tokens:
            if t not in stopwords and not es_numero_o_precio(t):
                return t

        return "producto"

    # ---------------------------------------------------------
    # Construcción del bloque del sistema
    # ---------------------------------------------------------
    def build_system_prompt(self, content):
        # COPILOT-change: Mejorar inclusión de contexto_previo para mantener historial conversacional
        partes = []

         # === 1. MEMORIA CONVERSACIONAL ===
        if self.contexto_previo:
            partes.append("### CONTEXTO PREVIO:")
            # COPILOT-add: Limitar contexto a últimas 10 interacciones para evitar sobrecarga
            contexto_limited = self.contexto_previo[-10:] if len(self.contexto_previo) > 10 else self.contexto_previo
            partes.append("\n".join(contexto_limited))
            partes.append("\n")
            
        if (content):
            mercancia = content[0]["mercancia"]
        else:
            mercancia = self.extract_mercancia(self.message)
        print (f">>>>>>>>> MERCANCIA: {mercancia} <<<<<<<<<<<<\n", flush=True)

        # -------------------------
        # BROKER COMPRADOR
        # -------------------------
        if self.role_broker == "comprador":
            partes.append("Eres un broker COMPRADOR. Tu tarea es evaluar compradores usando SOLO los datos dados.")
            partes.append("RESPONDE SOLO en español. No inventes datos.")

            partes.append("\nREGLA ABSOLUTA:")
            partes.append("- Muestra únicamente resultados que esten en la BASE DE DATOS.\n")
            partes.append("- Si hay compradores en la base de datos → listarlos uno por uno con:")
            partes.append("   nombre, mercancía solicitada, ubicación, estado.")
            partes.append("- PROHIBIDO decir que no hay resultados si la base NO está vacía.")
            partes.append("- Si está vacía → ofrece activar notificaciones.")
            partes.append("- NO mezcles productos: si la mercancía solicitada no coincide, no listes otros productos.")

            partes.append(f"\nMERCANCIA_SOLICITADA: {mercancia}")

            partes.append("\nDATOS_DE_LA_BASE_DE_DATOS:")
            if content:
                for item in content:
                    partes.append(f"-\n{self.format_item(item)}")
            else:
                partes.append("  (vacío)")

        # -------------------------
        # BROKER VENDEDOR
        # -------------------------
        elif self.role_broker == "vendedor":
            partes.append("Eres un broker VENDEDOR. Tu tarea es evaluar vendedores usando SOLO los datos dados.")
            partes.append("RESPONDE SOLO en español. No inventes datos.")

            partes.append("\nREGLA ABSOLUTA:")
            partes.append("- Muestra únicamente resultados que esten en la BASE DE DATOS.\n")
            partes.append("- Si hay vendedores en la base de datos → listarlos uno por uno con:")
            partes.append("   nombre, precio, ubicación, tamaños, domicilio, teléfono.")
            partes.append("- PROHIBIDO decir que no hay resultados si la base NO está vacía.")
            partes.append("- Si está vacía → ofrece activar notificaciones.")
            partes.append("- NO mezcles productos: si la mercancía solicitada no coincide, no listes otros productos.")

            partes.append(f"\nMERCANCIA_SOLICITADA: {mercancia}")

            partes.append("\nDATOS_DE_LA_BASE_DE_DATOS:")
            if content:
                for item in content:
                    partes.append(f"-\n{self.format_item(item)}")
            else:
                partes.append("  (vacío)")

        # -------------------------
        # BROKER TRANSPORTE
        # -------------------------
        elif self.role_broker == "transporte":
            partes.append("Eres un broker de TRANSPORTE. Tu tarea es coordinar traslado de productos o personas usando SOLO los datos dados.")
            partes.append("RESPONDE SOLO en español. No inventes datos.")

            partes.append("\nREGLA ABSOLUTA:")
            partes.append("- Muestra únicamente resultados que esten en la BASE DE DATOS.\n")
            partes.append("- Si hay transportistas en la base de datos → listarlos uno por uno con:")
            partes.append("   nombre, origen, destino, tipo de carga, estado.")
            partes.append("- PROHIBIDO decir que no hay resultados si la base NO está vacía.")
            partes.append("- Si está vacía → ofrece activar notificaciones.")
            partes.append("- NO mezcles servicios: si la mercancía solicitada no coincide, no listes otros transportes.")

            partes.append(f"\nMERCANCIA_SOLICITADA: {mercancia}")

            partes.append("\nDATOS_DE_LA_BASE_DE_DATOS:")
            if content:
                for item in content:
                    partes.append(f"-\n{self.format_item(item)}")
            else:
                partes.append("  (vacío)")

        # -------------------------
        # BROKER SERVICIO
        # -------------------------
        elif self.role_broker == "servicio":
            partes.append("Eres un broker de SERVICIOS. Tu tarea es coordinar solicitudes de servicio (ej. limpieza, reparación, asistencia) usando SOLO los datos dados.")
            partes.append("RESPONDE SOLO en español. No inventes datos.")

            partes.append("\nREGLA ABSOLUTA:")
            partes.append("- Muestra únicamente resultados que esten en la BASE DE DATOS.\n")
            partes.append("- Si hay servicios en la base de datos → listarlos uno por uno con:")
            partes.append("   nombre, tipo de servicio, ubicación, estado.")
            partes.append("- PROHIBIDO decir que no hay resultados si la base NO está vacía.")
            partes.append("- Si está vacía → ofrece activar notificaciones.")
            partes.append("- NO mezcles servicios: si el servicio solicitado no coincide, no listes otros.")

            partes.append(f"\nSERVICIO_SOLICITADO: {mercancia}")

            partes.append("\nDATOS_DE_LA_BASE_DE_DATOS:")
            if content:
                for item in content:
                    partes.append(f"-\n{self.format_item(item)}")
            else:
                partes.append("  (vacío)")

        # -------------------------
        # BROKER MENSAJERÍA
        # -------------------------
        elif self.role_broker == "mensajeria":
            partes.append("Eres un broker de MENSAJERÍA. Tu tarea es coordinar envíos y entregas usando SOLO los datos dados.")
            partes.append("RESPONDE SOLO en español. No inventes datos.")

            partes.append("\nREGLA ABSOLUTA:")
            partes.append("- Muestra únicamente resultados que esten en la BASE DE DATOS.\n")
            partes.append("- Si hay mensajeros en la base de datos → listarlos uno por uno con:")
            partes.append("   nombre, tipo de envío, origen, destino, estado.")
            partes.append("- PROHIBIDO decir que no hay resultados si la base NO está vacía.")
            partes.append("- Si está vacía → ofrece activar notificaciones.")
            partes.append("- NO mezcles servicios: si el envío solicitado no coincide, no listes otros.")

            partes.append(f"\nENVÍO_SOLICITADO: {mercancia}")

            partes.append("\nDATOS_DE_LA_BASE_DE_DATOS:")
            if content:
                for item in content:
                    partes.append(f"-\n{self.format_item(item)}")
            else:
                partes.append("  (vacío)")

        # -------------------------
        # BROKER NOTIFICACIÓN
        # -------------------------
        elif self.role_broker == "notificacion":
            partes.append("Eres un broker de NOTIFICACIONES. Tu tarea es registrar alertas para el usuario.")
            partes.append("RESPONDE SOLO en español. No inventes datos.")

            partes.append("\nREGLA ABSOLUTA:")
            partes.append("- Si el usuario pide notificación → confirma y registra la mercancía o servicio solicitado.")
            partes.append("- Si no hay contexto válido → responde que no hay notificación pendiente.")
            partes.append("- No inventes productos ni servicios.")

            partes.append(f"\nSOLICITUD_DE_NOTIFICACION: {mercancia}")

        # -------------------------
        # BROKER NEGOCIO
        # -------------------------
        elif self.role_broker == "negocio":
            partes.append("Eres un broker de NEGOCIOS. Tu tarea es ayudar al usuario a encontrar negocios físicos (ej. ferretería, barbería).")
            partes.append("RESPONDE SOLO en español. No inventes datos.")

            partes.append("\nREGLA ABSOLUTA:")
            partes.append("- Muestra únicamente resultados que esten en la BASE DE DATOS.\n")
            partes.append("- Si hay negocios en la base de datos → listarlos uno por uno con:")
            partes.append("   nombre, tipo de negocio, ubicación, estado.")
            partes.append("- PROHIBIDO decir que no hay resultados si la base NO está vacía.")
            partes.append("- Si está vacía → ofrece activar notificaciones.")
            partes.append("- NO mezcles negocios: si el tipo solicitado no coincide, no listes otros.")

            partes.append(f"\nNEGOCIO_SOLICITADO: {mercancia}")

            partes.append("\nDATOS_DE_LA_BASE_DE_DATOS:")
            if content:
                for item in content:
                    partes.append(f"-\n{self.format_item(item)}")
            else:
                partes.append("  (vacío)")

        else:
            partes.append("Error: rol no válido.")

        return "\n".join(partes)

    # ---------------------------------------------------------
    # Construcción del prompt final
    # ---------------------------------------------------------
    def reduce(self, full_prompt: str) -> str:
        # Construir el bloque dinámico del sistema
        system_block = self.build_system_prompt(self.content)

        # Combinar el prompt base (full_prompt) con el bloque reducido system_block
        # system_final = f"{full_prompt}\n\n# === BLOQUE REDUCIDO ===\n{system_block}"
        
        #print(f">>>>>>>>>> SYSTEM FINAL <<<<<<<<<<<<<<<<\n", flush=True)
        #print(f"{system_final}", flush=True)

        # Construir el prompt final en formato nativo de Qwen
        prompt_final = f"""
        <|im_start|>system
        {system_block}
        <|im_end|>

        <|im_start|>user
        {self.message}
        <|im_end|>

        <|im_start|>assistant
        """.strip()

        return prompt_final


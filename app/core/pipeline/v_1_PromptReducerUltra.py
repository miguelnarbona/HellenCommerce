import re
from collections import defaultdict
from itertools import combinations


class PromptReducerUltra:
    """
    Reductor ULTRA agresivo y estable.
    - Limpia JSON y datos dinámicos sin romper reglas
    - Reduce narrativa a lógica
    - Aplica equivalencias semánticas profundas
    - Aplica patrones lógicos (De Morgan, implicaciones)
    - Clasifica reglas por tema
    - Minimiza redundancias (versión segura)
    - Reconstruye en CNF/PROLOG-like
    """

    def __init__(self):

        # Frases sin valor lógico
        self.stop_phrases = [
            r"\bpor favor\b",
            r"\brecuerda que\b",
            r"\bten en cuenta\b",
            r"\bes importante que\b",
            r"\btu objetivo es\b",
            r"\btu tarea es\b",
            r"\bdebes\b",
            r"\bdeberías\b",
            r"\bse requiere que\b",
            r"\bno olvides\b",
            r"\basegúrate de\b",
        ]

        # Equivalencias semánticas → símbolos lógicos
        self.semantic_equivalences = {
            r"\bno inventes datos\b": "PROHIBIDO(inventar_datos)",
            r"\bno agregues información que no esté\b": "PROHIBIDO(info_fuera_DB)",
            r"\bno ignores\b": "PROHIBIDO(ignorar)",
            r"\busa exclusivamente\b": "USAR_SOLO(DB)",
            r"\busa solo\b": "USAR_SOLO(DB)",
            r"\bsi existe una mercancía detectada\b": "MERCANCIA_DETECTADA",
            r"\bsi existe un tipo de negocio detectado\b": "NEGOCIO_DETECTADO",
            r"\bsi hay\b": "SI_HAY",
            r"\bsi no hay\b": "SI_NO_HAY",
            r"\btexto plano\b": "FORMATO(texto_plano)",
            r"\bespañol\b": "FORMATO(espanol)",
        }

        # Patrones lógicos
        self.logical_patterns = [
            (r"no (.+?) y no (.+?)", r"¬(\1 ∨ \2)"),
            (r"si (.+?) entonces (.+?)", r"(\1) → (\2)"),
        ]

        # Macros
        self.macro_patterns = {
            r"intencion_detectada: compra": "INT=COMPRA",
            r"intencion_detectada: negocio": "INT=NEGOCIO",
            r"intencion_detectada: mensajeria": "INT=MENSAJERIA",
            r"intencion_detectada: transporte": "INT=TRANSPORTE",
            r"intencion_detectada: informativa": "INT=INFORMATIVA",
            r"intencion_detectada: otra": "INT=OTRA",
        }

    # -------------------------------------------------------------
    # Normalización
    # -------------------------------------------------------------
    def normalize(self, text: str) -> str:
        t = text.lower().strip()
        return re.sub(r"\s+", " ", t)

    # -------------------------------------------------------------
    # Filtrar JSON, datos_db, datos_rag, contexto, usuario
    # -------------------------------------------------------------
    def v_1_remove_dynamic_sections(self, text: str) -> str:

        # 1. QUEDARSE SOLO CON EL BLOQUE <sistema> ... </sistema>
        if "<sistema>" in text and "</sistema>" in text:
            text = text.split("<sistema>", 1)[1].split("</sistema>", 1)[0]

        # 2. ELIMINAR SOLO JSON REAL (no reglas)
        #    Esto elimina bloques que empiezan con { y terminan con }
        text = re.sub(r"\{[^{}]*\}", "", text)

        # 3. ELIMINAR SOLO LISTAS JSON (no listas del sistema)
        text = re.sub(r"\[[^\[\]]*\]", "", text)

        # 4. ELIMINAR SOLO LÍNEAS QUE PERTENECEN A datos_db o datos_rag
        cleaned = []
        for line in text.split("\n"):
            l = line.strip()

            # líneas típicas de DB
            if l.startswith("{") or l.startswith("}") or l.startswith('"'):
                continue

            if any(k in l for k in ["\"id\"", "\"user_id\"", "\"telefono\"", "\"correo\"", "\"lat\"", "\"lon\"", "\"estado\"", "\"contexto\""]):
                continue

            cleaned.append(line)

        return "\n".join(cleaned).strip()

    def remove_dynamic_sections(self, text: str) -> str:

        # 1. QUEDARSE SOLO CON EL BLOQUE <sistema> ... </sistema>
        if "<sistema>" in text and "</sistema>" in text:
            text = text.split("<sistema>", 1)[1].split("</sistema>", 1)[0]

        # 2. ELIMINAR SOLO JSON REAL (no reglas del sistema)
        text = re.sub(r"\{[\s\S]*?\}", "", text)
        text = re.sub(r"\[[\s\S]*?\]", "", text)

        cleaned = []
        for line in text.split("\n"):
            l = line.strip()

            # 3. ELIMINAR SOLO LÍNEAS QUE SON 100% JSON O DB
            #    (líneas que empiezan con {, }, o "campo": valor)
            if l.startswith("{") or l.startswith("}") or l.startswith('"'):
                continue

            # 4. ELIMINAR SOLO LÍNEAS QUE SON CAMPOS DB REALES
            #    (no palabras dentro de reglas)
            if re.match(r'^\s*"[a-zA-Z0-9_]+":', l):
                continue

            cleaned.append(line)

        return "\n".join(cleaned).strip()

    # -------------------------------------------------------------
    # Eliminar narrativa irrelevante
    # -------------------------------------------------------------
    def remove_stop_phrases(self, text: str) -> str:
        for sp in self.stop_phrases:
            text = re.sub(sp, "", text)
        return text

    # -------------------------------------------------------------
    # Sustituciones semánticas profundas
    # -------------------------------------------------------------
    def apply_semantic_equivalences(self, text: str) -> str:
        for pattern, replacement in self.semantic_equivalences.items():
            text = re.sub(pattern, replacement, text)
        return text

    # -------------------------------------------------------------
    # Patrones lógicos
    # -------------------------------------------------------------
    def apply_logical_patterns(self, text: str) -> str:
        for pattern, repl in self.logical_patterns:
            text = re.sub(pattern, repl, text)
        return text

    # -------------------------------------------------------------
    # Aplicar macros
    # -------------------------------------------------------------
    def apply_macros(self, text: str) -> str:
        for pattern, macro in self.macro_patterns.items():
            text = re.sub(pattern, macro, text)
        return text

    # -------------------------------------------------------------
    # Segmentar en reglas (sin romper JSON ni números)
    # -------------------------------------------------------------
    def split_into_rules(self, text: str):
        # Solo dividir por saltos de línea
        raw_parts = re.split(r"\n+", text)
        rules = [p.strip() for p in raw_parts if p.strip()]

        # Limitar tamaño para evitar loops
        return [r for r in rules if len(r) < 300]

    # -------------------------------------------------------------
    # Clasificación temática
    # -------------------------------------------------------------
    def classify_rule(self, rule: str) -> str:
        r = rule.lower()

        # REGLAS DB
        if "usar_solo" in r:
            return "DB"
        if r.startswith("- si existe el campo") or r.startswith("- cada elemento") or r.startswith("content:"):
            return "DB"
        if '"content"' in r:
            return "DB"

        # INTENCION
        if "int=" in r:
            return "INTENCION"
        if "mercancia_detectada" in r or "negocio_detectado" in r:
            return "INTENCION"
        if r.startswith("intenciones posibles"):
            return "INTENCION"
        if r.startswith("regla absoluta"):
            return "INTENCION"
        if r.startswith("- compra") or r.startswith("- negocio") or r.startswith("- mensajeria") or r.startswith("- transporte") or r.startswith("- informativa"):
            return "INTENCION"

        # PROHIBICIONES
        if "prohibido" in r:
            return "PROHIBICIONES"

        # CARDINALIDAD
        if "si_hay" in r:
            return "CARDINALIDAD"
        if "singular" in r or "plural" in r:
            return "CARDINALIDAD"

        # FORMATO
        if "formato(" in r or "formato " in r:
            return "FORMATO"

        # OTRAS
        return "OTRAS"

    def v_1_classify_rule(self, rule: str) -> str:

        if "usar_solo" in rule or "content" in rule:
            return "DB"

        if "int=" in rule or "compra" in rule or "negocio" in rule or "mensajeria" in rule or "transporte" in rule:
            return "INTENCION"

        if "prohibido" in rule:
            return "PROHIBICIONES"

        if "formato" in rule:
            return "FORMATO"

        if "singular" in rule or "plural" in rule:
            return "CARDINALIDAD"

        return "OTRAS"

    # -------------------------------------------------------------
    # Minimización booleana segura
    # -------------------------------------------------------------
    def boolean_minimize(self, rules: list) -> list:

        # Evitar explosión combinatoria
        if len(rules) > 80:
            return sorted(set(rules))

        minimized = set(rules)
        for a, b in combinations(rules, 2):
            if a != b:
                if a in b:
                    minimized.discard(b)
                elif b in a:
                    minimized.discard(a)
        return sorted(minimized)

    # -------------------------------------------------------------
    # Minimizar grupos
    # -------------------------------------------------------------
    def minimize_groups(self, groups):
        minimized = {}
        for key, rules in groups.items():
            # eliminar duplicados, mantener orden
            uniq = list(dict.fromkeys(rules))
            minimized[key] = uniq
        return minimized

    def v_1_minimize_groups(self, groups):
        minimized = {}
        for key, rules in groups.items():
            norm = set(re.sub(r"\s+", " ", r).strip() for r in rules)
            minimized[key] = self.boolean_minimize(list(norm))
        return minimized

    # -------------------------------------------------------------
    # Reconstrucción final
    # -------------------------------------------------------------
    def rebuild_prompt(self, groups):
        lines = []
        for section, title in [
            ("DB", "% REGLAS DB"),
            ("INTENCION", "% REGLAS INTENCION"),
            ("PROHIBICIONES", "% PROHIBICIONES"),
            ("CARDINALIDAD", "% CARDINALIDAD"),
            ("FORMATO", "% FORMATO"),
            ("OTRAS", "% OTRAS"),
        ]:
            if groups.get(section):
                lines.append(title)
                for r in groups[section]:
                    lines.append(f"{r}.")
        return "\n".join(lines)
    
    def preprocess_for_rules(self, text: str) -> str:
        # Saltos de línea después de puntos que cierran frase
        text = re.sub(r"\.(?!\d)", ".\n", text)

        # Saltos de línea después de guiones de reglas
        text = re.sub(r"-\s+", "- ", text)
        text = text.replace("- ", "\n- ")

        # Saltos de línea después de viñetas
        text = text.replace("•", "\n• ")

        # Normalizar múltiples saltos
        text = re.sub(r"\n+", "\n", text)

        return text.strip()

    def is_noise(self, rule: str) -> bool:
        r = rule.strip().lower()

        # líneas vacías o símbolos sueltos
        if r in {")", ").", "(", "(", ".", ".."}:
            return True

        # números sueltos
        if r.isdigit():
            return True

        # títulos sin contenido
        if r in {"2.", "3.", "4.", "5."}:
            return True

        # frases genéricas que no son reglas
        if r.startswith("eres un broker"):
            return True
        if r.startswith("ayudar al usuario"):
            return True
        if r.startswith("uso de la base de datos"):
            return True
        if r.startswith("respuesta"):
            return True
        if r.startswith("multi-intención"):
            return True

        return False
    
    def merge_broken_rules(self, rules: list) -> list:
        merged = []
        buffer = ""

        for r in rules:
            line = r.strip()

            # Si la línea es un fragmento suelto, la pegamos al buffer
            if line in {")", ").", "content:", "content:.", "intenciones posibles:."}:
                continue

            # Si empieza con ")" es un fragmento colgante → ignorar
            if line.startswith(")") or line.startswith(")."):
                continue

            # Si la línea empieza con "•" o "-" y hay buffer → es parte de la regla anterior
            if (line.startswith("•") or line.startswith("-")) and buffer:
                buffer += " " + line
                continue

            # Si la línea es muy corta y no es regla → ignorar
            if len(line) <= 2 and not line.startswith("-") and not line.startswith("•"):
                continue

            # Si hay buffer acumulado y llega una nueva regla → guardar buffer
            if buffer:
                merged.append(buffer)
                buffer = ""

            buffer = line

        # Guardar último buffer
        if buffer:
            merged.append(buffer)

        return merged
 
    # -------------------------------------------------------------
    # Reducción final ULTRA
    # -------------------------------------------------------------
    def reduce(self, full_prompt: str) -> str:
        t = self.normalize(full_prompt)
        t = self.preprocess_for_rules(t)
        t = self.remove_dynamic_sections(t)
        t = self.remove_stop_phrases(t)
        t = self.apply_semantic_equivalences(t)
        t = self.apply_logical_patterns(t)
        t = self.apply_macros(t)

        rules = self.split_into_rules(t)

        # 1. Filtrar ruido
        clean_rules = [r for r in rules if not self.is_noise(r)]

        # 2. Recomponer reglas partidas
        merged_rules = self.merge_broken_rules(clean_rules)

        # 3. Clasificar
        groups = defaultdict(list)
        for r in merged_rules:
            groups[self.classify_rule(r)].append(r)

        # 4. Minimizar sin destruir
        groups = self.minimize_groups(groups)

        # 5. Reconstruir prompt final
        return self.rebuild_prompt(groups)


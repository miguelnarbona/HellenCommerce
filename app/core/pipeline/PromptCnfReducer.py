import re
from collections import defaultdict
from typing import List, Dict

# Normaliza
# Elimina ruido
# Aplica equivalencias semánticas
# Aplica patrones lógicos (implicaciones, De Morgan)
# Agrupa reglas por tema
# Minimiza redundancias dentro de cada grupo
# Genera algo cercano a una CNF “humana”
# Usa una capa de “macros” para compactar aún más

class PromptCnfReducer:
    """
    Reductor lógico-formal agresivo de prompts.
    Aplica:
      - Normalización lingüística
      - Eliminación de ruido
      - Sustitución semántica
      - Patrones lógicos (De Morgan, implicaciones)
      - Agrupación temática
      - Minimización de redundancias
      - Compresión con macros simbólicas
      - Salida tipo reglas (casi CNF/PROLOG-like)
    """

    def __init__(self):
        # Frases sin valor lógico fuerte
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
            r"\basegúrate de\b",
            r"\bno olvides\b",
        ]

        # Equivalencias semánticas → símbolos lógicos / macros
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
            r"\bsi \"content\" contiene vendedores o negocios válidos\b": "CONTENT_NO_VACIO",
            r"\bsi \"content\" está vacío o no existe\b": "CONTENT_VACIO",
        }

        # Patrones lógicos (De Morgan, implicaciones)
        self.logical_patterns = [
            (r"no (.+?) y no (.+?)", r"¬(\1 ∨ \2)"),
            (r"si (.+?) entonces (.+?)", r"(\1) → (\2)"),
        ]

        # Macros para agrupar reglas recurrentes
        self.macro_patterns = {
            r"intencion_detectada: compra": "INT=COMPRA",
            r"intencion_detectada: negocio": "INT=NEGOCIO",
            r"intencion_detectada: mensajeria": "INT=MENSAJERIA",
            r"intencion_detectada: transporte": "INT=TRANSPORTE",
            r"intencion_detectada: informativa": "INT=INFORMATIVA",
            r"intencion_detectada: otra": "INT=OTRA",
        }

    # -------------------------------------------------------------
    # Normalización básica
    # -------------------------------------------------------------
    def normalize(self, text: str) -> str:
        t = text.lower().strip()
        t = re.sub(r"\s+", " ", t)
        return t

    # -------------------------------------------------------------
    # Eliminar frases sin contenido lógico fuerte
    # -------------------------------------------------------------
    def remove_stop_phrases(self, text: str) -> str:
        t = text
        for sp in self.stop_phrases:
            t = re.sub(sp, "", t)
        return t

    # -------------------------------------------------------------
    # Sustituir equivalencias semánticas
    # -------------------------------------------------------------
    def apply_semantic_equivalences(self, text: str) -> str:
        t = text
        for pattern, replacement in self.semantic_equivalences.items():
            t = re.sub(pattern, replacement, t)
        return t

    # -------------------------------------------------------------
    # Aplicar patrones lógicos (De Morgan, implicaciones)
    # -------------------------------------------------------------
    def apply_logical_patterns(self, text: str) -> str:
        t = text
        for pattern, repl in self.logical_patterns:
            t = re.sub(pattern, repl, t)
        return t

    # -------------------------------------------------------------
    # Aplicar macros simbólicas
    # -------------------------------------------------------------
    def apply_macros(self, text: str) -> str:
        t = text
        for pattern, macro in self.macro_patterns.items():
            t = re.sub(pattern, macro, t)
        return t

    # -------------------------------------------------------------
    # Segmentar en "reglas" (líneas lógicas)
    # -------------------------------------------------------------
    def split_into_rules(self, text: str) -> List[str]:
        # Cortamos por puntos, saltos de línea y etiquetas
        raw_parts = re.split(r"[.\n]", text)
        rules = []
        for part in raw_parts:
            p = part.strip()
            if not p:
                continue
            rules.append(p)
        return rules

    # -------------------------------------------------------------
    # Clasificar reglas por tema (heurístico)
    # -------------------------------------------------------------
    def classify_rule(self, rule: str) -> str:
        r = rule

        if "usar_solo" in r or "USAR_SOLO" in r or "content" in r or "db" in r:
            return "DB"

        if "intencion" in r or "INT=" in r or "compra" in r or "negocio" in r \
           or "mensajeria" in r or "transporte" in r or "informativa" in r:
            return "INTENCION"

        if "prohibido" in r or "PROHIBIDO" in r:
            return "PROHIBICIONES"

        if "respuesta" in r or "formato" in r or "salida" in r \
           or "texto plano" in r or "español" in r:
            return "FORMATO"

        if "singular" in r or "plural" in r or "|db|" in r or "cardinalidad" in r:
            return "CARDINALIDAD"

        return "OTRAS"

    # -------------------------------------------------------------
    # Minimizar reglas por grupo (eliminar redundancias)
    # -------------------------------------------------------------
    def minimize_groups(self, groups: Dict[str, List[str]]) -> Dict[str, List[str]]:
        minimized = {}
        for key, rules in groups.items():
            # Normalizar espacios y eliminar duplicados exactos
            norm = set()
            for r in rules:
                r_clean = re.sub(r"\s+", " ", r).strip()
                if r_clean:
                    norm.add(r_clean)
            minimized[key] = sorted(norm)
        return minimized

    # -------------------------------------------------------------
    # Reconstruir prompt reducido en forma lógica
    # -------------------------------------------------------------
    def rebuild_prompt(self, groups: Dict[str, List[str]]) -> str:
        lines = []

        if "DB" in groups and groups["DB"]:
            lines.append("% REGLAS SOBRE USO DE DB")
            for r in groups["DB"]:
                lines.append(f"{r}.")

        if "INTENCION" in groups and groups["INTENCION"]:
            lines.append("\n% REGLAS SOBRE INTENCION")
            for r in groups["INTENCION"]:
                lines.append(f"{r}.")

        if "PROHIBICIONES" in groups and groups["PROHIBICIONES"]:
            lines.append("\n% REGLAS DE PROHIBICION")
            for r in groups["PROHIBICIONES"]:
                lines.append(f"{r}.")

        if "CARDINALIDAD" in groups and groups["CARDINALIDAD"]:
            lines.append("\n% REGLAS DE CARDINALIDAD")
            for r in groups["CARDINALIDAD"]:
                lines.append(f"{r}.")

        if "FORMATO" in groups and groups["FORMATO"]:
            lines.append("\n% REGLAS DE FORMATO DE RESPUESTA")
            for r in groups["FORMATO"]:
                lines.append(f"{r}.")

        if "OTRAS" in groups and groups["OTRAS"]:
            lines.append("\n% OTRAS REGLAS")
            for r in groups["OTRAS"]:
                lines.append(f"{r}.")

        return "\n".join(lines)

    # -------------------------------------------------------------
    # Reducción final agresiva
    # -------------------------------------------------------------
    def reduce(self, full_prompt: str) -> str:
        t = self.normalize(full_prompt)
        t = self.remove_stop_phrases(t)
        t = self.apply_semantic_equivalences(t)
        t = self.apply_logical_patterns(t)
        t = self.apply_macros(t)

        rules = self.split_into_rules(t)

        groups: Dict[str, List[str]] = defaultdict(list)
        for r in rules:
            g = self.classify_rule(r)
            groups[g].append(r)

        groups = self.minimize_groups(groups)
        reduced = self.rebuild_prompt(groups)
        return reduced

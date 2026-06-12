import re
from typing import List

# Análisis sintáctico
# Normalización semántica
# Factorización lógica
# Reducción por equivalencias
# Aplicación de De Morgan
# Conversión a reglas tipo PROLOG
# Reconstrucción del prompt reducido

class PromptReducer:
    """
    Reductor lógico-formal de prompts.
    Aplica:
      - Normalización lingüística
      - Factorización semántica
      - Reducción por equivalencias lógicas
      - Leyes de De Morgan
      - Reescritura tipo PROLOG
      - Eliminación de redundancias
    """

    def __init__(self):
        # Palabras que no aportan contenido lógico
        self.stop_phrases = [
            r"\bpor favor\b",
            r"\bten en cuenta que\b",
            r"\brecuerda que\b",
            r"\bes importante que\b",
            r"\bdebes\b",
            r"\bdeberías\b",
            r"\bse requiere que\b",
            r"\btu objetivo es\b",
            r"\btu tarea es\b",
        ]

        # Normalizaciones semánticas
        self.semantic_equivalences = {
            r"\bno inventes datos\b": "prohibido(inventar_datos)",
            r"\bno ignores\b": "prohibido(ignorar)",
            r"\busa exclusivamente\b": "usar_solo",
            r"\bsi existe\b": "si_existe",
            r"\bsi hay\b": "si_hay",
            r"\bsi no hay\b": "si_no_hay",
            r"\bsi existe una mercancía detectada\b": "mercancia_detectada",
            r"\bsi existe un tipo de negocio detectado\b": "negocio_detectado",
        }

        # Reglas que pueden factorizarse
        self.logical_patterns = [
            (r"no (.+?) y no (.+?)", r"¬(\1 ∨ \2)"),  # De Morgan
            (r"si (.+?) entonces (.+?)", r"(\1) → (\2)"),
        ]

    # -------------------------------------------------------------
    # 1. Normalización básica
    # -------------------------------------------------------------
    def normalize(self, text: str) -> str:
        t = text.lower().strip()
        t = re.sub(r"\s+", " ", t)
        return t

    # -------------------------------------------------------------
    # 2. Eliminar frases sin contenido lógico
    # -------------------------------------------------------------
    def remove_stop_phrases(self, text: str) -> str:
        t = text
        for sp in self.stop_phrases:
            t = re.sub(sp, "", t)
        return t

    # -------------------------------------------------------------
    # 3. Sustituir equivalencias semánticas
    # -------------------------------------------------------------
    def apply_semantic_equivalences(self, text: str) -> str:
        t = text
        for pattern, replacement in self.semantic_equivalences.items():
            t = re.sub(pattern, replacement, t)
        return t

    # -------------------------------------------------------------
    # 4. Aplicar patrones lógicos (De Morgan, implicaciones, etc.)
    # -------------------------------------------------------------
    def apply_logical_patterns(self, text: str) -> str:
        t = text
        for pattern, repl in self.logical_patterns:
            t = re.sub(pattern, repl, t)
        return t

    # -------------------------------------------------------------
    # 5. Convertir reglas en formato PROLOG-like
    # -------------------------------------------------------------
    def convert_to_prolog(self, text: str) -> str:
        lines = text.split(".")
        rules = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detectar reglas tipo "si X → Y"
            m = re.match(r"\((.+?)\) → \((.+?)\)", line)
            if m:
                rules.append(f"{m.group(2)} :- {m.group(1)}.")
                continue

            # Detectar prohibiciones
            if "prohibido(" in line:
                rules.append(f"{line}.")
                continue

            # Detectar afirmaciones simples
            if "usar_solo" in line:
                rules.append("usar_solo(DB).")
                continue

            rules.append(line + ".")

        return "\n".join(rules)

    # -------------------------------------------------------------
    # 6. Reducción final
    # -------------------------------------------------------------
    def reduce(self, full_prompt: str) -> str:
        t = self.normalize(full_prompt)
        t = self.remove_stop_phrases(t)
        t = self.apply_semantic_equivalences(t)
        t = self.apply_logical_patterns(t)
        t = self.convert_to_prolog(t)
        return t

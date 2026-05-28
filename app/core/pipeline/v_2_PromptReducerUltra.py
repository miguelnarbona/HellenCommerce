import re
from collections import defaultdict
from itertools import combinations


class PromptReducerUltra:

    # -----------------------------
    # NORMALIZACIÓN
    # -----------------------------
    def normalize(self, text: str) -> str:
        text = text.lower()
        text = text.replace("\t", " ")
        text = text.replace("  ", " ")
        return text.strip()

    # -----------------------------
    # PREPROCESADO PARA REGLAS
    # -----------------------------
    def preprocess_for_rules(self, text: str) -> str:
        import re
        text = re.sub(r"\.(?!\d)", ".\n", text)
        text = text.replace("- ", "\n- ")
        text = text.replace("•", "\n• ")
        text = re.sub(r"\n+", "\n", text)
        return text.strip()

    # -----------------------------
    # SPLIT EN LÍNEAS
    # -----------------------------
    def split_into_rules(self, text: str):
        return [l.strip() for l in text.split("\n") if l.strip()]

    # -----------------------------
    # FILTRO DE RUIDO
    # -----------------------------
    def is_noise(self, rule: str) -> bool:
        r = rule.strip().lower()

        if r in {")", ").", "(", ".", ".."}:
            return True
        if r in {"2.", "3.", "4.", "5."}:
            return True
        if r.isdigit():
            return True

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

    # -----------------------------
    # RECOMPONER REGLAS PARTIDAS
    # -----------------------------
    def merge_broken_rules(self, rules: list) -> list:
        merged = []
        buffer = ""

        for r in rules:
            line = r.strip()

            if line in {"content:", "content:.", "intenciones posibles:."}:
                continue
            if line.startswith(")") or line.startswith(")."):
                continue
            if (line.startswith("•") or line.startswith("-")) and buffer:
                buffer += " " + line
                continue
            if len(line) <= 2 and not line.startswith("-") and not line.startswith("•"):
                continue

            if buffer:
                merged.append(buffer)
                buffer = ""

            buffer = line

        if buffer:
            merged.append(buffer)

        return merged

    # -----------------------------
    # CLASIFICACIÓN
    # -----------------------------
    def classify_rule(self, rule: str) -> str:
        r = rule.lower().strip()

        if "usar_solo" in r:
            return "DB"
        if r.startswith("- si existe el campo") or r.startswith("- cada elemento") or r.startswith("content:"):
            return "DB"
        if '"content"' in r:
            return "DB"

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

        if "prohibido" in r:
            return "PROHIBICIONES"

        if "si_hay" in r or "singular" in r or "plural" in r:
            return "CARDINALIDAD"

        if "formato(" in r or "formato " in r:
            return "FORMATO"

        return "OTRAS"

    # -----------------------------
    # MINIMIZACIÓN SEGURA
    # -----------------------------
    def minimize_groups(self, groups):
        minimized = {}
        for key, rules in groups.items():
            uniq = list(dict.fromkeys(rules))
            minimized[key] = uniq
        return minimized

    # -----------------------------
    # REDUCCIÓN SEMÁNTICA (SRM)
    # -----------------------------
    def semantic_reduce_groups(self, groups):
        final = {}

        # DB
        if "DB" in groups:
            final["DB"] = [
                "- usar_solo(db) la información de datos_db.",
                "- si existe 'content', úsalo como lista de resultados.",
                "- cada elemento de 'content' es un vendedor o negocio válido.",
                "- prohibido(inventar_datos), prohibido(info_fuera_db), prohibido(ignorar 'content').",
                "- si 'content' tiene resultados → respóndelos.",
                "- si 'content' está vacío → ofrece activar notificaciones."
            ]

        # INTENCION — SIEMPRE INCLUIRLA
        final["INTENCION"] = [
            "- mercancia_detectada + vendedores → int=compra.",
            "- negocio_detectado + negocios → int=negocio.",
            "- nunca uses int=otra ni int=informatica cuando hay vendedores o negocios.",
            "- compra, negocio, mensajeria, transporte, informativa, otra.",
            "- compra + mensajeria → mensajeria.",
            "- compra + transporte → transporte.",
            "al final agrega: intencion_detectada: <valor>."
        ]

        # PROHIBICIONES
        if "PROHIBICIONES" in groups:
            final["PROHIBICIONES"] = [
                "- prohibido(inventar_datos).",
                "- prohibido modificar, resumir o ignorar información de content."
            ]

        # CARDINALIDAD
        if "CARDINALIDAD" in groups:
            final["CARDINALIDAD"] = [
                "- si_hay 1 resultado → singular.",
                "- si_hay varios → plural y listarlos uno por uno."
            ]

        # FORMATO
        if "FORMATO" in groups:
            final["FORMATO"] = [
                "- formato(texto_plano).",
                "- responde solo en español.",
                "- usa formato consistente y profesional."
            ]

        # OTRAS
        final["OTRAS"] = [
            "- presenta los resultados claramente.",
            "- incluye contexto previo solo si aporta datos útiles.",
            "- si el usuario pidió teléfono o ubicación, muéstralos si existen.",
            "- si es compra → sugiere contactar al vendedor.",
            "- si es negocio → sugiere visitar o contactar el negocio."
        ]

        return final
        
    def remove_stop_phrases(self, text: str) -> str:
        STOP = [
            "este es el contexto",
            "a continuación",
            "como modelo de lenguaje",
            "respuesta generada",
            "instrucciones del sistema"
        ]
        for s in STOP:
            text = text.replace(s, " ")
        return text.strip()
    
    def apply_semantic_equivalences(self, text: str) -> str:
        eq = {
            "vendedor": "vendedor",
            "negocio": "negocio",
            "comprar": "compra",
            "busco": "compra",
            "necesito": "compra",
            "quiero": "compra",
            "tienes": "compra",
            "hay": "compra"
        }
        for k, v in eq.items():
            text = text.replace(k, v)
        return text

    def apply_logical_patterns(self, text: str) -> str:
        # Normaliza flechas, guiones, símbolos
        text = text.replace("→", "->")
        text = text.replace("=>", "->")
        text = text.replace("–", "-")
        return text

    def apply_macros(self, text: str) -> str:
        # Macro simple: normalizar espacios y saltos
        import re
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    
    def remove_dynamic_sections(self, text: str) -> str:
        # Elimina JSON, diccionarios, arrays, bloques con llaves o corchetes
        text = re.sub(r"\{[^{}]*\}", " ", text)
        text = re.sub(r"\[[^\[\]]*\]", " ", text)
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    # -----------------------------
    # RECONSTRUCCIÓN FINAL
    # -----------------------------
    def rebuild_prompt(self, groups):
        out = []
        for key, rules in groups.items():
            out.append(f"% {key}")
            for r in rules:
                out.append(r)
        return "\n".join(out)

    # -----------------------------
    # PIPELINE COMPLETO
    # -----------------------------
    def reduce(self, full_prompt: str) -> str:
        t = self.normalize(full_prompt)
        t = self.preprocess_for_rules(t)
        t = self.remove_dynamic_sections(t)
        t = self.remove_stop_phrases(t)
        t = self.apply_semantic_equivalences(t)
        t = self.apply_logical_patterns(t)
        t = self.apply_macros(t)

        rules = self.split_into_rules(t)
        clean = [r for r in rules if not self.is_noise(r)]
        merged = self.merge_broken_rules(clean)

        groups = defaultdict(list)
        for r in merged:
            groups[self.classify_rule(r)].append(r)

        groups = self.minimize_groups(groups)
        groups = self.semantic_reduce_groups(groups)

        return self.rebuild_prompt(groups)

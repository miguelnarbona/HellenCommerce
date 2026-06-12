import re
from collections import defaultdict


class PromptReducerUltra:
    def __init__(self, content=None, contexto_previo=None):
        self.content = content
        self.contexto_previo = contexto_previo

    # ============================================================
    #  BLOQUE 1 — UTILIDADES BÁSICAS
    # ============================================================

    def _extract_between(self, text, header):
        """
        Extrae el bloque dinámico después de un encabezado.
        """
        pattern = rf"{header}\s*(\{{.*?\}}|\[.*?\]|.*?)(?=\n[A-Z]|$)"
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1).strip() if m else ""

    def _replace_block(self, text, header, placeholder):
        """
        Reemplaza el bloque dinámico por un marcador compacto.
        """
        pattern = rf"{header}\s*(\{{.*?\}}|\[.*?\]|.*?)(?=\n[A-Z]|$)"
        return re.sub(pattern, f"{header}\n{placeholder}", text, flags=re.DOTALL)

    # ============================================================
    #  BLOQUE 2 — EXTRACCIÓN DE PLACEHOLDERS
    # ============================================================

    def extract_dynamic_blocks(self, full_prompt: str):
        return {
            "DB_JSON": self._extract_between(full_prompt, "DATOS DE LA BASE DE DATOS (limpios):"),
            "RAG_JSON": self._extract_between(full_prompt, "DATOS ADICIONALES:"),
            "CTX_JSON": self._extract_between(full_prompt, "CONTEXTO PREVIO:"),
            "ROL": self._extract_between(full_prompt, "ROL DEL USUARIO:"),
            "MERCANCIA": self._extract_between(full_prompt, "MERCANCÍA DETECTADA:")
        }

    def compress_placeholders(self, full_prompt: str):
        compressed = full_prompt
        compressed = self._replace_block(compressed, "DATOS DE LA BASE DE DATOS (limpios):", "<DB_JSON>")
        compressed = self._replace_block(compressed, "DATOS ADICIONALES:", "<RAG_JSON>")
        compressed = self._replace_block(compressed, "CONTEXTO PREVIO:", "<CTX_JSON>")
        compressed = self._replace_block(compressed, "ROL DEL USUARIO:", "<ROL>")
        compressed = self._replace_block(compressed, "MERCANCÍA DETECTADA:", "<MERCANCIA>")
        return compressed

    def restore_placeholders(self, reduced_prompt: str, blocks: dict):
        final = reduced_prompt
        final = final.replace("<DB_JSON>", blocks["DB_JSON"])
        final = final.replace("<RAG_JSON>", blocks["RAG_JSON"])
        final = final.replace("<CTX_JSON>", blocks["CTX_JSON"])
        final = final.replace("<ROL>", blocks["ROL"])
        final = final.replace("<MERCANCIA>", blocks["MERCANCIA"])
        return final

    # ============================================================
    #  BLOQUE 3 — REDUCCIÓN SOLO DEL BLOQUE <sistema>
    # ============================================================

    def _extract_system_block(self, full_prompt: str):
        m = re.search(r"<sistema>(.*?)</sistema>", full_prompt, re.DOTALL | re.IGNORECASE)
        if not m:
            return None, full_prompt, None, None
        before = full_prompt[:m.start(1)]
        system_block = m.group(1)
        after = full_prompt[m.end(1):]
        return system_block, before, after, m

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
    # final = final.replace("<DB_JSON>", blocks["DB_JSON"])
    # final = final.replace("<RAG_JSON>", blocks["RAG_JSON"])
    # final = final.replace("<CTX_JSON>", blocks["CTX_JSON"])
    # final = final.replace("<ROL>", blocks["ROL"])
    # final = final.replace("<MERCANCIA>", blocks["MERCANCIA"])
    
    def classify_rule(self, rule: str) -> str:
        r = rule.lower().strip()

        if "content" in r or "datos de la base de datos" in r or "base de datos" in r:
            return r"DB"

        if "int=" in r or "intencion" in r or "mercancia_detectada" in r:
            return r"INTENCION"

        if "prohibido" in r:
            return r"PROHIBICIONES"

        if "si hay" in r or "singular" in r or "plural" in r:
            return r"CARDINALIDAD"

        if "formato" in r:
            return r"FORMATO"

        return r"OTRAS"

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
    # REDUCCIÓN SEMÁNTICA (SIEMPRE INCLUYE DB)
    # -----------------------------
    def semantic_reduce_groups(self, groups=None):
        return {
            "CORE": [
                "Usa exclusivamente los datos proporcionados.",
                "No inventes información.",
                "Responde en texto plano, profesional y directo.",
                "Al final agrega: intencion_detectada:<valor>."
            ]
        }

    def v_2_semantic_reduce_groups(
        self,
        groups: dict[str, list[str]],
        max_rules_per_group: int = 2,
        max_chars_per_rule: int = 140,
        max_total_chars: int = 1200,
    ) -> dict[str, list[str]]:

        reduced = {}

        # 1. Reducir cada grupo
        for name, rules in groups.items():
            if not rules:
                continue

            kept = []

            # Tomar solo las primeras reglas importantes
            for r in rules[:max_rules_per_group]:
                r = r.strip()

                # Recorte duro por regla
                if len(r) > max_chars_per_rule:
                    r = r[:max_chars_per_rule].rstrip() + "..."

                # Limpieza mínima
                r = r.replace("•", "-")
                r = " ".join(r.split())

                kept.append(r)

            reduced[name] = kept

        # 2. Si el total excede el límite, recortar grupos enteros
        def total_chars(d):
            return sum(len(x) for v in d.values() for x in v)

        while total_chars(reduced) > max_total_chars:
            # eliminar el grupo más largo
            longest = max(reduced, key=lambda k: sum(len(x) for x in reduced[k]))
            del reduced[longest]

        return reduced

    def V_1_semantic_reduce_groups(self, groups):
        final = {}

        # SIEMPRE incluir DB
        final["DB"] = [
            "- usar_solo(db) la información de datos_db.",
            "- si existe 'content', úsalo como lista de resultados.",
            "- cada elemento de 'content' es un vendedor o negocio válido.",
            "- prohibido(inventar_datos), prohibido(info_fuera_db), prohibido(ignorar 'content').",
            "- si 'content' tiene resultados → respóndelos.",
            "- si 'content' está vacío → ofrece activar notificaciones."
        ]

        # SIEMPRE incluir INTENCION
        final["INTENCION"] = [
            "- mercancia_detectada + vendedores → int=compra.",
            "- negocio_detectado + negocios → int=negocio.",
            "- nunca uses int=otra ni int=informatica cuando hay vendedores o negocios.",
            "- compra, negocio, mensajeria, transporte, informativa, otra.",
            "- compra + mensajeria → mensajeria.",
            "- compra + transporte → transporte.",
            "al final agrega: intencion_detectada: <valor>."
        ]

        # SIEMPRE incluir OTRAS
        final["OTRAS"] = [
            "- presenta los resultados claramente.",
            "- incluye contexto previo solo si aporta datos útiles.",
            "- si el usuario pidió teléfono o ubicación, muéstralos si existen.",
            "- si es compra → sugiere contactar al vendedor.",
            "- si es negocio → sugiere visitar o contactar el negocio."
        ]

        return final

    # -----------------------------
    # MÉTODOS FALTANTES (YA INCLUIDOS)
    # -----------------------------
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
            "comprar": "compra",
            "busco": "compra",
            "necesito": "compra",
            "quiero": "compra",
            "tienes": "compra",
            "hay": "compra",
            "negocio": "negocio",
            "vendedor": "vendedor"
        }
        for k, v in eq.items():
            text = text.replace(k, v)
        return text

    def apply_logical_patterns(self, text: str) -> str:
        text = text.replace("→", "->")
        text = text.replace("=>", "->")
        text = text.replace("–", "-")
        return text

    def apply_macros(self, text: str) -> str:
        # Compacta espacios dentro de líneas, pero NO toca saltos de línea
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
        return "\n".join(lines)

    # -----------------------------
    # RECONSTRUCCIÓN DE BLOQUE REDUCIDO
    # -----------------------------
    def build_system_prompt(self, reduced, content, contexto_previo):
        partes = []

        # Caso 1: hay vendedores/negocios
        if content:
            partes.append("Eres un asistente. Usa exclusivamente estos datos para responder:")
            for item in content:
                # Puedes formatearlo como quieras, aquí va simple:
                partes.append(f"- {item}")
        else:
            # Caso 2: no hay resultados
            partes.append("Eres un asistente. No hay resultados en la base de datos.")
            if contexto_previo:
                partes.append(f"Contexto previo relevante: {contexto_previo}")
            partes.append("Ofrece activar notificaciones.")

        # Reglas mínimas hardcodeadas
        partes.append("\nREGLAS MINIMAS:")
        partes.extend(reduced["CORE"])

        return "\n".join(partes)

    def v_2_build_system_prompt(self, reduced):
        partes = []

        partes.append(
            "Eres un broker que conecta compradores con vendedores y negocios locales. "
            "Debes usar solo los datos de la base de datos y seguir estas reglas."
        )

        if "DB" in reduced:
            partes.append("\nREGLAS DE BASE DE DATOS:")
            partes.extend(reduced["DB"])

        if "INTENCION" in reduced:
            partes.append("\nREGLAS DE INTENCIÓN:")
            partes.extend(reduced["INTENCION"])

        if "CARDINALIDAD" in reduced:
            partes.append("\nREGLAS DE CARDINALIDAD:")
            partes.extend(reduced["CARDINALIDAD"])

        if "FORMATO" in reduced:
            partes.append("\nFORMATO DE SALIDA:")
            partes.extend(reduced["FORMATO"])

        if "OTRAS" in reduced:
            partes.append("\nOTRAS REGLAS:")
            partes.extend(reduced["OTRAS"])

        return "\n".join(partes)

    def v_1_rebuild_prompt(self, groups):
        out = []
        for key, rules in groups.items():
            out.append(f"% {key}")
            for r in rules:
                out.append(r)
        return "\n".join(out)

    # -----------------------------
    # REDUCE SOLO EL BLOQUE <sistema>
    # -----------------------------
    def _reduce_system_block(self, system_block: str) -> str:
        # Decoradores Evolutions
        print(f">>> EVOLUTIONS INITIALS PROMPT: {system_block}", flush= True)

        # Poner todo en minusculas
        t = self.normalize(system_block)
        print(f">>> EVOLUTIONS self.normalize(t) PROMPT: {t}\n", flush= True)

        t = self.preprocess_for_rules(t)
        print(f">>> EVOLUTIONS self.preprocess_for_rules(t) PROMPT: {t}\n", flush= True)

        # Aqui ya hay problemas Las reglas dicen 1. y todas las que son puntos les da retorno
        # al igual que a 1.
        t = self.remove_stop_phrases(t)
        print(f">>> EVOLUTIONS self.remove_stop_phrases(t) PROMPT: {t}\n", flush= True)

        t = self.apply_semantic_equivalences(t)
        print(f">>> EVOLUTIONS self.apply_semantic_equivalences(t) PROMPT: {t}\n", flush= True)

        t = self.apply_logical_patterns(t)
        print(f">>> EVOLUTIONS self.apply_logical_patterns(t) PROMPT: {t}\n", flush= True)

        t = self.apply_macros(t)
        print(f">>> EVOLUTIONS self.apply_macros(t) PROMPT: {t}\n", flush= True)

        rules = self.split_into_rules(t)
        print(f">>> EVOLUTIONS self.split_into_rules(t) PROMPT: {rules}\n", flush= True)

        # De aqui en adelante nada funciona
        clean = [r for r in rules if not self.is_noise(r)]
        print(f">>> EVOLUTIONS self.is_noise(r) PROMPT: {clean}\n", flush= True)

        merged = self.merge_broken_rules(clean)
        print(f">>> EVOLUTIONS self.merge_broken_rules(clean) PROMPT: {merged}\n", flush= True)

        groups = defaultdict(list)
        for r in merged:
            groups[self.classify_rule(r)].append(r)
        print(f">>> EVOLUTIONS self.classify_rule(r) PROMPT: {groups}\n", flush= True)

        groups = self.minimize_groups(groups)
        print(f">>> EVOLUTIONS self.minimize_groups(groups) PROMPT: {groups}\n", flush= True)

        reduced = self.semantic_reduce_groups(groups)
        print(f">>> EVOLUTIONS self.semantic_reduce_groups(groups) PROMPT: {groups}\n", flush= True)

        # print(f">>> EVOLUTIONS self.build_system_prompt(reduced) PROMPT: {self.build_system_prompt(reduced)}\n", flush= True)
        return self.build_system_prompt(
            reduced,
            content=self.content,
            contexto_previo=self.contexto_previo
            )

    # ============================================================
    #  BLOQUE 4 — PIPELINE COMPLETO
    # ============================================================
    def reduce(self, full_prompt: str) -> str:
        # Ignoramos full_prompt completamente
        groups = {}  # ya no se usa
        reduced = self.semantic_reduce_groups(groups)

        return self.build_system_prompt(
            reduced,
            self.content,
            self.contexto_previo
        )

    def v_1_reduce(self, full_prompt: str) -> str:

        # 1. Extraer bloques dinámicos
        blocks = self.extract_dynamic_blocks(full_prompt)

        # 2. Comprimir placeholders
        compressed = self.compress_placeholders(full_prompt)

        # 3. Extraer bloque <sistema>
        system_block, before, after, m = self._extract_system_block(compressed)

        if system_block is None:
            reduced_system = self._reduce_system_block(compressed)
            print(f">>> self._reduce_system_block(compressed) == {reduced_system}\n", flush=True)
            final = reduced_system
        else:
            reduced_system = self._reduce_system_block(system_block)
            print(f">>> self._reduce_system_block(compressed) == {reduced_system}\n", flush=True)
            final = before + reduced_system + after

        # 4. Restaurar JSON y placeholders originales
        final = self.restore_placeholders(final, blocks)

        return final

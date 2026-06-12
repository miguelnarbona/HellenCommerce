# core/pipeline/InfoExtractor.py

import re
import os

from config.settings import Config
from app.core.pipeline.nlp_loader import nlp

class InfoExtractor:

    def __init__(self):
        self.keywords_buy = self._load_keywords(Config.KEYWORDS_BUY)
        self.keywords_sell = self._load_keywords(Config.KEYWORDS_SELL)
        self.keywords_ntfy = self._load_keywords(Config.KEYWORDS_NTFY)

        # Cargar spaCy
        self.nlp = nlp

        # Mensajes que NO deben resetear mercancía
        self.detalle_patterns = [
            "su numero", "su número", "su telefono", "su teléfono",
            "dame su", "darme su", "contacto", "como lo contacto",
            "ubicacion", "ubicación", "direccion", "dirección"
        ]

        # Mapa semántico extendido
        self.semantic_map = {
            "negocio": {
                "barberia", "heladeria", "cafeteria", "panaderia",
                "ferreteria", "peluqueria", "bodega"
            },
            "servicio": {
                "corte de pelo", "corte", "reparacion", "mensajeria",
                "entrega", "envio"
            },
            "categoria": {
                "comida", "bebida", "dulces", "postres", "belleza", "herramientas"
            }
        }

    # ---------------------------------------------------------
    # Cargar palabras clave desde archivo
    # ---------------------------------------------------------
    def _load_keywords(self, path: str):
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]

    # ---------------------------------------------------------
    # Extracción principal
    # ---------------------------------------------------------
    def extract(self, message: str) -> dict:
        print(f">>> Extrayendo información de mensaje: '{message}'", flush=True)
        text = message.lower().strip()
        info = {}

        # ---------------------------------------------------------
        # 0) DETECCIÓN DE MENSAJES QUE NO DEBEN CAMBIAR MERCANCÍA
        # ---------------------------------------------------------
        # Pero primero verificar si contiene mercancía nueva
        # Ej: "dame el contacto de un vendedor de arroz" tiene "dame" + "arroz"
        mercancia_nueva = self._extraer_mercancia_keywords(text)
        if not mercancia_nueva:
            mercancia_nueva = self._extraer_mercancia_fallback(text)

        if any(re.search(rf"\b{re.escape(p)}\b", text) for p in self.detalle_patterns):
            # Si hay mercancia nueva, NO es confirmación pura
            if mercancia_nueva:
                info["mercancia"] = self._normalizar_mercancia_final(mercancia_nueva)
                info["accion"] = "nueva_busqueda_con_detalle"
                return info
            info["accion"] = "confirmacion"
            info["mercancia"] = None
            return info

        # ---------------------------------------------------------
        # 1) DETECCIÓN DE ACEPTACIÓN DE NOTIFICACIONES
        # ---------------------------------------------------------
        patrones_regex = [
            r"\bnotificame\b", r"\bnotifícame\b",
            r"\bavisame\b", r"\bavísame\b",
            "quiero que me avises", "quiero que me notifiques",
            "quiero recibir alertas", "quiero recibir avisos",
            "me gustaría recibir notificaciones",
            r"si[, ]*notifícame", r"si[, ]*notificame",
            r"si[, ]*avisame", r"si[, ]*avísame",
            "activa mis notificaciones", "activa mis avisos", "activa mis alertas"
        ]

        if any(k in text for k in self.keywords_ntfy):
            return {"accion": "aceptar_notificaciones", "mercancia": None}

        if any(re.search(p, text) for p in patrones_regex):
            return {"accion": "aceptar_notificaciones", "mercancia": None}

        # ---------------------------------------------------------
        # 2) DETECCIÓN DE CONFIRMACIÓN
        # ---------------------------------------------------------
        confirmaciones = {
            "pásame", "pasame", "dame", "envíame", "enviame",
            "quiero los datos", "datos del vendedor", "contacto",
            "pásame los datos", "pasame los datos", "pásame el contacto",
            "si", "sí", "ok"
        }

        if any(re.search(rf"\b{re.escape(c)}\b", text) for c in confirmaciones):
            # Si tiene mercancia nueva extraída arriba, usarla
            if mercancia_nueva:
                info["mercancia"] = self._normalizar_mercancia_final(mercancia_nueva)
                info["accion"] = "nueva_busqueda_con_detalle"
                return info
            return {"accion": "confirmacion", "mercancia": None}

        # ---------------------------------------------------------
        # 3) PRECIO
        # ---------------------------------------------------------
        precio = re.search(r"(\d+)\s*(usd|mn|eur|dólar|dolares|pesos)?", text)
        if precio:
            try:
                info["precio"] = int(precio.group(1))
            except:
                info["precio"] = None

        # ---------------------------------------------------------
        # 4) TAMAÑOS
        # ---------------------------------------------------------
        tamanos = []

        pulgadas = re.search(r"(\d+(\.\d+)?)\s*pulgadas", text)
        if pulgadas:
            tamanos.append(pulgadas.group(1))

        patrones_tamano = [
            r"talla\s*(\d+)",
            r"size\s*(\d+)",
            r"(pequeño|mediano|grande)"
        ]

        for p in patrones_tamano:
            m = re.search(p, text)
            if m:
                tamanos.append(m.group(1) if m.group(1) else m.group(0))

        info["tamaños"] = ",".join(tamanos) if tamanos else ""

        # ---------------------------------------------------------
        # 5) UBICACIÓN
        # ---------------------------------------------------------
        patrones_ubicacion = [
            r"en\s+([a-zñáéíóú\s]+)",
            r"ubicad[oa]\s+en\s+([a-zñáéíóú\s]+)",
            r"zona\s+([a-zñáéíóú\s]+)",
            r"vivo en\s+([a-zñáéíóú\s]+)"
        ]

        info["ubicacion"] = None
        for p in patrones_ubicacion:
            m = re.search(p, text)
            if m:
                info["ubicacion"] = m.group(1).strip()
                break

        # ---------------------------------------------------------
        # 6) TELÉFONO
        # ---------------------------------------------------------
        tel = re.search(r"\b\d{7,10}\b", text)
        info["telefono"] = tel.group(0) if tel else None

        # ---------------------------------------------------------
        # 7) CORREO
        # ---------------------------------------------------------
        mail = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
        info["correo"] = mail.group(0) if mail else None

        # ---------------------------------------------------------
        # 8) ENTREGA A DOMICILIO
        # ---------------------------------------------------------
        info["domicilio"] = 1 if ("domicilio" in text or "entrega" in text) else 0

        # ---------------------------------------------------------
        # 9) MERCANCÍA (POS-tagging + fallback)
        # ---------------------------------------------------------
        # Reutilizar mercancia_nueva ya extraída al inicio
        if mercancia_nueva:
            mercancia = self._normalizar_mercancia_final(mercancia_nueva)
            info["mercancia"] = mercancia
        else:
            info["mercancia"] = None

        # ---------------------------------------------------------
        # 10) CLASIFICACIÓN SEMÁNTICA
        # ---------------------------------------------------------
        info["negocio"] = None
        info["servicio"] = None
        info["categoria"] = None

        if info["mercancia"] is None:
            nucleo = self._extraer_nucleo(text)

            if nucleo:
                for tipo, valores in self.semantic_map.items():
                    if nucleo in valores:
                        info[tipo] = nucleo
                        break

        return info

    # ---------------------------------------------------------
    # MERCANCÍA por keywords BUY/SELL (POS-tagging)
    # ---------------------------------------------------------
    def _extraer_mercancia_keywords(self, text: str):
        print("\n====== DEBUG _extraer_mercancia_keywords (POS) ======", flush=True)
        print("TEXT:", repr(text), flush=True)

        doc = self.nlp(text)
        keywords = set(self.keywords_buy + self.keywords_sell)

        print("KEYWORDS:", keywords, flush=True)

        tokens = list(doc)

        for i, token in enumerate(tokens):
            if token.text.lower() in keywords:
                mercancía_tokens = []

                for j in range(i + 1, len(tokens)):
                    t = tokens[j]

                    if t.pos_ in ("VERB", "AUX"):
                        break

                    if t.pos_ in ("NOUN", "PROPN"):
                        mercancía_tokens.append(t.text)
                        continue

                    if t.pos_ == "ADJ" and mercancía_tokens:
                        mercancía_tokens.append(t.text)
                        continue

                    if t.pos_ in ("DET", "PRON", "ADV"):
                        continue

                    break

                if mercancía_tokens:
                    raw = " ".join(mercancía_tokens)
                    print("RAW_MERCANCIA:", raw, flush=True)
                    cleaned = self._limpiar_mercancia(raw)
                    print("CLEANED:", cleaned, flush=True)
                    return cleaned

        return None

    # ---------------------------------------------------------
    # MERCANCÍA fallback semántico
    # ---------------------------------------------------------
    def _extraer_mercancia_fallback(self, text: str):
        doc = self.nlp(text)
        candidatos = []

        for token in doc:
            if token.pos_ in ("NOUN", "PROPN"):
                candidatos.append(token.text)

        if not candidatos:
            return None

        raw = " ".join(candidatos[:3])
        return self._limpiar_mercancia(raw)

    # ---------------------------------------------------------
    # Limpieza de mercancía
    # ---------------------------------------------------------
    def _limpiar_mercancia(self, text: str):
        if not text:
            return None

        STOPWORDS = {
            "una", "un", "uno", "unas", "unos",
            "algun", "alguna", "algunas", "algunos",
            "la", "el", "los", "las",
            "porfa", "porfavor", "por", "favor",
            "mi", "tu", "su",
            "quiero", "busco", "necesito", "tendras", "tienes", "hay",
            "anda", "ando", "buscando",
            "me", "dame", "pasame", "pásame",
            "podras", "podrás", "puedes", "podrias", "podrías", "puede",
            "hola", "oye", "buenas"
        }

        palabras = text.lower().split()
        filtradas = [p for p in palabras if p not in STOPWORDS]

        if not filtradas:
            return None

        return " ".join(filtradas).strip()

    # ---------------------------------------------------------
    # Normalización final
    # ---------------------------------------------------------
    def _normalizar_mercancia_final(self, mercancia: str) -> str:
        palabras = mercancia.split()
        if palabras and palabras[0] in {"un", "una", "uno", "unos", "unas"}:
            palabras = palabras[1:]
        return " ".join(palabras).strip()

    # ---------------------------------------------------------
    # Núcleo semántico
    # ---------------------------------------------------------
    def _extraer_nucleo(self, text: str):
        tokens = text.split()
        if not tokens:
            return None
        return tokens[-1]

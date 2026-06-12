# core/pipeline/InfoExtractor.py

import re
import os
from config.settings import Config


class InfoExtractor:

    def __init__(self):
        self.keywords_buy = self._load_keywords(Config.KEYWORDS_BUY)
        self.keywords_sell = self._load_keywords(Config.KEYWORDS_SELL)
        self.keywords_ntfy = self._load_keywords(Config.KEYWORDS_NTFY)

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
        if any(re.search(rf"\b{re.escape(p)}\b", text) for p in self.detalle_patterns):
            info["accion"] = "confirmacion"
            info["mercancia"] = None
            return info

        # ---------------------------------------------------------
        # 1) DETECCIÓN DE ACEPTACIÓN DE NOTIFICACIONES
        # ---------------------------------------------------------
        patrones_regex = [
            r"\bnotificame\b", r"\bnotifícame\b",
            r"\bavisame\b", r"\bavísame\b",
            r"quiero que me avises", "quiero que me notifiques",
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
        # 2) DETECCIÓN DE CONFIRMACIÓN (NO CAMBIA MERCANCÍA)
        # ---------------------------------------------------------
        confirmaciones = {
            "pásame", "pasame", "dame", "envíame", "enviame",
            "quiero los datos", "datos del vendedor", "contacto",
            "pásame los datos", "pasame los datos", "pásame el contacto",
            "si", "sí", "ok"
        }

        if any(re.search(rf"\b{re.escape(c)}\b", text) for c in confirmaciones):
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
        # 9) MERCANCÍA (keywords dinámicas + fallback)
        # ---------------------------------------------------------
        mercancia = self._extraer_mercancia_keywords(text)
        if not mercancia:
            mercancia = self._extraer_mercancia_fallback(text)

        if mercancia:
            mercancia = self._normalizar_mercancia_final(mercancia)
            info["mercancia"] = mercancia
        else:
            info["mercancia"] = None

        # ---------------------------------------------------------
        # 10) CLASIFICACIÓN SEMÁNTICA (solo si NO hay mercancía)
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
    # MERCANCÍA por keywords BUY/SELL
    # ---------------------------------------------------------
    def _extraer_mercancia_keywords(self, text: str):
        print("\n====== DEBUG _extraer_mercancia_keywords ======", flush=True)
        print("TEXT:", repr(text), flush=True)

        # SOLO keywords raíz, nunca compuestos
        patrones = []

        if self.keywords_buy:
            patrones.extend(self.keywords_buy)
        if self.keywords_sell:
            patrones.extend(self.keywords_sell)

        print("PATRONES:", patrones, flush=True)

        if not patrones:
            return None

        # REGEX: keyword + cualquier cosa después
        pattern = (
            r"(?<!\w)("
            + "|".join(re.escape(k) for k in patrones)
            + r")(?!\w)\s+([a-zA-Zñáéíóú0-9\s]+)"
        )

        print("REGEX:", pattern, flush=True)

        m = re.search(pattern, text, flags=re.IGNORECASE)
        print("MATCH:", m.group(0) if m else None, flush=True)

        if not m:
            return None

        # grupo 2 = mercancía completa
        raw = m.group(2)
        print("RAW_MERCANCIA:", raw, flush=True)

        cleaned = self._limpiar_mercancia(raw)
        print("CLEANED:", cleaned, flush=True)

        return cleaned or None
    
    # ---------------------------------------------------------
    # MERCANCÍA fallback semántico
    # ---------------------------------------------------------
    def _extraer_mercancia_fallback(self, text: str):
        patrones = [
            r"\b(busco|compro|quiero|necesito|ando buscando|tendras|tienes|hay)\b[\s,]+([a-zA-Zñáéíóú0-9\s]+)",
            r"\b(vendo|ofrezco|tengo)\b[\s,]+([a-zA-Zñáéíóú0-9\s]+)"
        ]

        for p in patrones:
            m = re.search(p, text)
            if m:
                # limpiamos SOLO la mercancía, no el verbo
                return self._limpiar_mercancia(m.group(2))

        return None
    
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
            "una", "mi", "tu", "su",
            "quiero", "busco", "necesito", "tendras", "tienes", "hay",
            "anda", "ando", "buscando",
            "me", "dame", "pasame", "pásame",
            "hola", "oye", "buenas"
        }

        palabras = text.lower().split()
        filtradas = [p for p in palabras if p not in STOPWORDS]

        if not filtradas:
            return None

        return " ".join(filtradas).strip()
        
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

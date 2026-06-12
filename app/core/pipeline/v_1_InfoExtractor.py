# core/pipeline/InfoExtractor.py

import re
import os
from config.settings import Config


class InfoExtractor:

    def __init__(self):
        self.keywords_buy = self._load_keywords(Config.KEYWORDS_BUY)
        self.keywords_sell = self._load_keywords(Config.KEYWORDS_SELL)
        self.keywords_ntfy = self._load_keywords(Config.KEYWORDS_NTFY)

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
    def extract(self, text: str) -> dict:
        text = text.lower().strip()
        info = {}

        # ---------------------------------------------------------
        # DETECCIÓN DE ACEPTACIÓN DE NOTIFICACIONES
        # (archivo + patrones inteligentes)
        # ---------------------------------------------------------
        patrones_regex = [
            r"\bnotificame\b",
            r"\bnotifícame\b",
            r"\bavisame\b",
            r"\bavísame\b",
            r"quiero que me avises",
            r"quiero que me notifiques",
            r"quiero recibir alertas",
            r"quiero recibir avisos",
            r"me gustaría recibir notificaciones",
            r"si[, ]*notifícame",
            r"si[, ]*notificame",
            r"si[, ]*avisame",
            r"si[, ]*avísame",
            r"activa mis notificaciones",
            r"activa mis avisos",
            r"activa mis alertas"
        ]

        # 1) Coincidencia con archivo KEYWORDS_NTFY
        if any(k in text for k in self.keywords_ntfy):
            info["accion"] = "aceptar_notificaciones"
            info["mercancia"] = None
            return info

        # 2) Coincidencia con patrones regex
        if any(re.search(p, text) for p in patrones_regex):
            info["accion"] = "aceptar_notificaciones"
            info["mercancia"] = None
            return info

        # ---------------------------------------------------------
        # DETECCIÓN DE CONFIRMACIÓN
        # ---------------------------------------------------------
        confirmaciones = {
            "pásame", "pasame", "dame", "envíame", "enviame",
            "quiero los datos", "datos del vendedor", "contacto",
            "pásame los datos", "pasame los datos", "pásame el contacto",
            "si", "sí", "ok"
        }

        if any(re.search(rf"\b{re.escape(c)}\b", text) for c in confirmaciones):
            info["accion"] = "confirmacion"
            info["mercancia"] = None
            return info

        # ---------------------------------------------------------
        # PRECIO
        # ---------------------------------------------------------
        precio = re.search(r"(\d+)\s*(usd|mn|eur|dólar|dolares|pesos)?", text)
        if precio:
            try:
                info["precio"] = int(precio.group(1))
            except:
                info["precio"] = None

        # ---------------------------------------------------------
        # TAMAÑOS
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
        # UBICACIÓN
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
        # TELÉFONO
        # ---------------------------------------------------------
        tel = re.search(r"\b\d{7,10}\b", text)
        info["telefono"] = tel.group(0) if tel else None

        # ---------------------------------------------------------
        # CORREO
        # ---------------------------------------------------------
        mail = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
        info["correo"] = mail.group(0) if mail else None

        # ---------------------------------------------------------
        # ENTREGA A DOMICILIO
        # ---------------------------------------------------------
        info["domicilio"] = 1 if ("domicilio" in text or "entrega" in text) else 0

        # ---------------------------------------------------------
        # MERCANCÍA (keywords dinámicas)
        # ---------------------------------------------------------
        mercancia = self._extraer_mercancia_keywords(text)
        if mercancia:
            info["mercancia"] = mercancia
            return info

        # ---------------------------------------------------------
        # MERCANCÍA (fallback semántico)
        # ---------------------------------------------------------
        mercancia = self._extraer_mercancia_fallback(text)
        if mercancia:
            info["mercancia"] = mercancia
            return info

        # ---------------------------------------------------------
        # ÚLTIMO RECURSO
        # ---------------------------------------------------------
        palabras = text.split()
        candidatos = [p for p in palabras if len(p) > 3]
        if candidatos:
            info["mercancia"] = " ".join(candidatos[-3:])

        return info

    # ---------------------------------------------------------
    # MERCANCÍA por keywords BUY/SELL
    # ---------------------------------------------------------
    def _extraer_mercancia_keywords(self, text: str):
        # BUY
        if self.keywords_buy:
            pattern = r"(" + "|".join(re.escape(k) for k in self.keywords_buy) + r")\s+([a-zA-Zñáéíóú0-9\s]+)"
            m = re.search(pattern, text)
            if m:
                return self._limpiar_mercancia(m.group(2))

        # SELL
        if self.keywords_sell:
            pattern = r"(" + "|".join(re.escape(k) for k in self.keywords_sell) + r")\s+([a-zA-Zñáéíóú0-9\s]+)"
            m = re.search(pattern, text)
            if m:
                return self._limpiar_mercancia(m.group(2))

        return None

    # ---------------------------------------------------------
    # MERCANCÍA fallback semántico
    # ---------------------------------------------------------
    def _extraer_mercancia_fallback(self, text: str):
        patrones = [
            r"(busco|compro|quiero|necesito|ando buscando|tendras|tienes|hay)\s+([a-zA-Zñáéíóú0-9\s]+)",
            r"(vendo|ofrezco|tengo)\s+([a-zA-Zñáéíóú0-9\s]+)"
        ]

        for p in patrones:
            m = re.search(p, text)
            if m:
                return self._limpiar_mercancia(m.group(2))

        return None

    # ---------------------------------------------------------
    # Limpieza de mercancía
    # ---------------------------------------------------------
    def _limpiar_mercancia(self, texto: str):
        texto = texto.lower().strip()

        # Palabras que NO deben aparecer como parte de la mercancía
        STOPWORDS = {
            "hola", "oye", "buenas",
            "tendras", "tendrás", "tienes", "hay",
            "busco", "compro", "quiero", "necesito",
            "anda", "ando", "buscando",
            "disponible", "disponibles",
            "porfa", "porfavor", "por favor", "un",
            ",", ".", "con", "para", "en", "y", "e", 
            "ni", "que", "o", "u", "per", "disponible", 
            "mas", "sino", "aunque", "a", "ante", "bajo", 
            "con", "contra", "de", "desde", "durante", "entre", "hacia", 
            "hasta", "mediante", "para", "por", "segun", "sin", "so", "sobre",
            "versus", "via", "tras"
        }

        # 1. Eliminar signos y puntuación
        texto = re.sub(r"[?¡!.,;:]", " ", texto)

        # 2. Tokenizar
        palabras = texto.split()

        # 3. Eliminar stopwords
        palabras = [p for p in palabras if p not in STOPWORDS]

        # 4. NO limitar palabras, NO cortar por conectores
        #    porque la descripción puede ser larga
        return " ".join(palabras).strip()

    def v_1_limpiar_mercancia(self, texto: str):
        texto = texto.strip()
        texto = re.split(r"[,.]| con | para | en | y | e | ni | que | o | u | per | disponible \
                         | mas | sino | aunque | a | ante | bajo | con | contra | de | desde | durante | entre | hacia \
                         |  hasta | mediante | para | por | segun | sin | so | sobre | versus | via | tras", texto)[0]
        return texto.strip()
    

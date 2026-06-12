# core/pipeline/ResponseFormatter.py

import re

class ResponseFormatter:
    """
    Limpia y normaliza la respuesta generada por el modelo IA.
    Se encarga de:
    - Eliminar marcas no deseadas (USUARIO:, IA:, etc.)
    - Quitar espacios sobrantes
    - Corregir saltos de línea
    - Evitar repeticiones o ruido típico de modelos LLM
    """

    def __init__(self):
        # Marcadores que deben eliminarse si aparecen en la salida del modelo
        self.unwanted_markers = [
            "USUARIO (buyer):",
            "USUARIO (seller):",
            "USUARIO:",
            "IA (buyer):",
            "IA (seller):",
            "IA:",
            "Cliente:",
            "Vendedor:"
        ]

    # ---------------------------------------------------------
    # Limpieza principal
    # ---------------------------------------------------------
    def clean(self, text: str) -> str:
        if not text:
            return ""

        cleaned = text.strip()

        # Eliminar marcadores no deseados
        for marker in self.unwanted_markers:
            cleaned = cleaned.replace(marker, "")

        # Eliminar múltiples saltos de línea
        cleaned = re.sub(r"\n{2,}", "\n", cleaned)

        # Eliminar espacios repetidos
        cleaned = re.sub(r"\s{2,}", " ", cleaned)

        # Quitar basura generada por modelos (</s>, ###, etc.)
        cleaned = cleaned.replace("</s>", "").replace("###", "")

        return cleaned.strip()

    # ---------------------------------------------------------
    # Método principal usado por el Builder
    # ---------------------------------------------------------
    def format(self, text: str) -> str:
        """
        Punto de entrada estándar.
        """
        return self.clean(text)
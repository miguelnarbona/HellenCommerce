# core/pipeline/RoleDetector.py

import os
from config.settings import Config

class RoleDetector:
    """
    Detecta el rol del usuario (buyer o seller) con persistencia inteligente.
    NO cambia el rol si el mensaje no contiene mercancía o si es un mensaje de detalle.
    """

    def __init__(self):
        self.keywords_buy = self._load_keywords(Config.KEYWORDS_BUY)
        self.keywords_sell = self._load_keywords(Config.KEYWORDS_SELL)

        # Mensajes que NO deben cambiar el rol
        self.detalle_patterns = [
            "su numero", "su número", "su telefono", "su teléfono",
            "dame su", "darme su", "contacto", "como lo contacto",
            "ubicacion", "ubicación", "direccion", "dirección",
            "ok", "si", "sí", "perfecto", "bien", "gracias"
        ]

    # ---------------------------------------------------------
    # Carga de palabras clave
    # ---------------------------------------------------------
    def _load_keywords(self, path: str):
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]

    # ---------------------------------------------------------
    # Detección principal
    # ---------------------------------------------------------
    def detect(self, message: str, last_role: str = "buyer") -> str:
        """
        Determina el rol del usuario:
        - buyer  → comprador
        - seller → vendedor
        """

        msg = message.lower().strip()

        # ---------------------------------------------------------
        # 1) Mensajes que NO deben cambiar el rol
        # ---------------------------------------------------------
        if any(p in msg for p in self.detalle_patterns):
            return last_role

        # ---------------------------------------------------------
        # 2) Prefijos explícitos
        # ---------------------------------------------------------
        if msg.startswith("cliente:"):
            return "buyer"
        if msg.startswith("vendedor:"):
            return "seller"

        # ---------------------------------------------------------
        # 3) Palabras clave de compradores
        #    SOLO si el mensaje contiene mercancía
        # ---------------------------------------------------------
        if any(k in msg for k in self.keywords_buy):
            # Evitar falsos positivos como "tienes su número?"
            if not any(p in msg for p in self.detalle_patterns):
                return "buyer"

        # ---------------------------------------------------------
        # 4) Palabras clave de vendedores
        #    SOLO si el mensaje contiene mercancía
        # ---------------------------------------------------------
        if any(k in msg for k in self.keywords_sell):
            if not any(p in msg for p in self.detalle_patterns):
                return "seller"

        # ---------------------------------------------------------
        # 5) Fallback seguro: mantener rol previo
        # ---------------------------------------------------------
        return last_role

# core/pipeline/RoleDetector.py

import os
from config.settings import Config

class RoleDetector:
    """
    Detecta el rol del usuario (buyer o seller) basándose en:
    - Palabras clave
    - Prefijos explícitos ("cliente:", "vendedor:")
    - Rol anterior (fallback)
    """

    def __init__(self):
        self.keywords_buy = self._load_keywords(Config.KEYWORDS_BUY)
        self.keywords_sell = self._load_keywords(Config.KEYWORDS_SELL)

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

        # Prefijos explícitos
        if msg.startswith("cliente:"):
            return "buyer"
        if msg.startswith("vendedor:"):
            return "seller"

        # Palabras clave de compradores
        if any(k in msg for k in self.keywords_buy):
            return "buyer"

        # Palabras clave de vendedores
        if any(k in msg for k in self.keywords_sell):
            return "seller"

        # Si no se detecta nada, mantener el rol anterior
        return last_role
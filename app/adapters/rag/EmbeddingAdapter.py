"""
HellenCommerce - EmbeddingAdapter
Genera embeddings remotamente via HuggingFace Inference API.

Elimina dependencias locales de PyTorch / sentence-transformers.
Modelo: sentence-transformers/all-MiniLM-L6-v2  →  384 dimensiones.

Caché LRU (maxsize=512, ~1.5 MB RAM):
  - Solo evita re-llamar la API para el MISMO texto exacto en la misma sesión.
  - No afecta la frescura de las respuestas del LLM ni genera comentarios repetitivos.
  - El modelo online tiene prioridad absoluta para cualquier texto nuevo o modificado.
"""

import os
import functools
import numpy as np
from huggingface_hub import InferenceClient

_MODEL_NAME  = "sentence-transformers/all-MiniLM-L6-v2"
_CACHE_MAX   = 512   # 512 × 384 floats × 8 bytes ≈ 1.5 MB


def _pool_and_normalize(raw) -> list:
    """
    Convierte la salida cruda de feature_extraction a vector 384-dim normalizado.
    Maneja las tres formas posibles que devuelve la HF Inference API:
      - (1, seq_len, 384)  →  mean-pool sobre seq_len
      - (seq_len, 384)     →  mean-pool sobre seq_len
      - (384,)             →  ya pooled, solo normalizar
    """
    arr = np.array(raw, dtype=float)
    if arr.ndim == 3:       # (1, seq_len, hidden)
        vec = arr[0].mean(axis=0)
    elif arr.ndim == 2:     # (seq_len, hidden)
        vec = arr.mean(axis=0)
    elif arr.ndim == 1:     # (hidden,) ya pooled
        vec = arr
    else:
        raise ValueError(f"Forma de embedding inesperada de la API: {arr.shape}")

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


class EmbeddingAdapter:
    """
    Adaptador de embeddings 100% remoto via HuggingFace Inference API.

    Interfaz pública idéntica al EmbeddingAdapter original:
      embed(text)        → list[float]  (384 dims)
      embed_many(texts)  → list[list[float]]
      load()             → no-op (compatibilidad)
      get_model_name()   → str

    Variables de entorno:
      HF_API_KEY  — Token de HuggingFace (opcional para modelos públicos,
                    recomendado para evitar rate-limits).
    """

    def __init__(self, model_name: str = _MODEL_NAME, normalize: bool = True):
        self.model_name  = model_name
        self.normalize   = normalize
        self._api_key    = os.getenv("HF_API_KEY", "")
        self._client     = InferenceClient(token=self._api_key or None)
        print(f"✅ EmbeddingAdapter online → modelo: {model_name}", flush=True)

    # ----------------------------------------------------------
    # Compatibilidad hacia atrás (no-ops)
    # ----------------------------------------------------------
    def load(self):
        """No-op: el modelo reside en la nube de HuggingFace."""
        pass

    def _ensure_model_loaded(self):
        """No-op: el modelo reside en la nube de HuggingFace."""
        pass

    # ----------------------------------------------------------
    # Embedding único (con caché LRU por texto exacto)
    # ----------------------------------------------------------
    def embed(self, text: str) -> list:
        if not isinstance(text, str):
            raise TypeError("El texto debe ser un string.")
        if not text.strip():
            raise ValueError("El texto no puede estar vacío.")
        return self._embed_cached(text)

    @functools.lru_cache(maxsize=_CACHE_MAX)
    def _embed_cached(self, text: str) -> list:
        """
        Llama a la HF Inference API y devuelve el vector normalizado.
        La caché LRU garantiza que textos idénticos no generen llamadas
        duplicadas, pero cada texto nuevo siempre consulta el modelo online.
        """
        raw = self._client.feature_extraction(text, model=self.model_name)
        return _pool_and_normalize(raw)

    # ----------------------------------------------------------
    # Embedding múltiple
    # ----------------------------------------------------------
    def embed_many(self, texts: list) -> list:
        if not isinstance(texts, list) or not texts:
            raise ValueError("texts debe ser una lista no vacía de strings.")
        if not all(isinstance(t, str) and t.strip() for t in texts):
            raise ValueError("Todos los textos deben ser strings no vacíos.")
        return [self._embed_cached(t) for t in texts]

    # ----------------------------------------------------------
    # Utilidades
    # ----------------------------------------------------------
    def get_model_name(self) -> str:
        return self.model_name

    def clear_cache(self):
        """Invalida la caché LRU manualmente si se requiere frescura total."""
        self._embed_cached.cache_clear()
        print("🔄 Caché LRU de embeddings limpiada.", flush=True)

import config
from sentence_transformers import SentenceTransformer
import threading


class EmbeddingAdapter:
    """
    Adaptador para generar embeddings usando SentenceTransformers.
    Optimizado para uso con Chroma Server (HTTP) y CPU.
    """

    def __init__(self, model_name="all-MiniLM-L6-v2", normalize=True):
        self.model_name = model_name
        self.model = None
        self.normalize = normalize
        self.path_model = config.settings.Config.MODEL_PATH_MINI
        self._lock = threading.Lock()

    # ---------------------------------------------------------
    # Carga explícita (para startup_event)
    # ---------------------------------------------------------
    def load(self):
        with self._lock:
            if self.model is None:
                print(">>> Cargando modelo de embeddings MiniLM...")
                self.model = SentenceTransformer(
                    model_name_or_path=self.path_model,
                    device="cpu"
                )
                print(">>> MiniLM cargado correctamente.")

    # ---------------------------------------------------------
    # Carga perezosa (solo si no se llamó load())
    # ---------------------------------------------------------
    def _ensure_model_loaded(self):
        if self.model is None:
            self.load()

    # ---------------------------------------------------------
    # Embedding para un solo texto
    # ---------------------------------------------------------
    def embed(self, text: str):
        if not isinstance(text, str):
            raise TypeError("El texto debe ser un string.")
        if not text.strip():
                raise ValueError("El texto no puede estar vacío.")

        self._ensure_model_loaded()

        vector = self.model.encode(
            [text],
            normalize_embeddings=self.normalize
        )[0]

        return vector.tolist()

    # ---------------------------------------------------------
    # Embedding para múltiples textos
    # ---------------------------------------------------------
    def embed_many(self, texts: list):
        if not isinstance(texts, list):
            raise TypeError("texts debe ser una lista de strings.")
        if not texts:
            raise ValueError("La lista de textos está vacía.")
        if not all(isinstance(t, str) and t.strip() for t in texts):
            raise ValueError("Todos los textos deben ser strings no vacíos.")

        self._ensure_model_loaded()

        vectors = self.model.encode(
            texts,
            batch_size=16,
            normalize_embeddings=self.normalize
        )

        return [v.tolist() for v in vectors]

    def get_model_name(self):
        return self.model_name

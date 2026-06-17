# config/settings.py

import os


class Settings:
    """
    Configuración centralizada del proyecto.
    Compatible con Docker y con ejecución local.
    """

    # -----------------------------
    # Rutas base del proyecto
    # -----------------------------
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # -----------------------------
    # Modelos IA (montados como volúmenes en Docker)
    # -----------------------------
    MODEL_PATH      = os.getenv("MODEL_PATH")
    MODEL_PATH_MINI = os.getenv("EMBEDDINGS_PATH")   # ya no usado por EmbeddingAdapter; se preserva por compatibilidad

    MODEL_N_CTX     = 4096
    MODEL_N_THREADS = 8

    # -----------------------------
    # Base de datos SQLite
    # -----------------------------
    SQLITE_DB_PATH = os.getenv("SQLITE_PATH")

    # -----------------------------
    # Directorio de prompts
    # -----------------------------
    PROMPT_DIR    = os.path.join(BASE_DIR, "resources", "prompts")
    PROMPT_BUYER  = os.path.join(PROMPT_DIR, "broker_prompt_comprador.txt")
    PROMPT_SELLER = os.path.join(PROMPT_DIR, "broker_prompt_vendedor.txt")
    PROMPT_SYSTEM = os.path.join(PROMPT_DIR, "system_base.txt")

    # -----------------------------
    # Archivos de palabras clave
    # -----------------------------
    KEYWORDS_BUY  = os.path.join(BASE_DIR, "app/resources", "keywords_buy.txt")
    KEYWORDS_SELL = os.path.join(BASE_DIR, "app/resources", "keywords_sel.txt")
    KEYWORDS_NTFY = os.path.join(BASE_DIR, "app/resources", "keywords_ntfy.txt")

    # -----------------------------
    # ChromaDB (backend local — preservado)
    # -----------------------------
    CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb_service")
    CHROMA_PORT = int(os.getenv("CHROMA_PORT", 8000))

    # -----------------------------
    # Routing del backend vectorial
    # "chromadb" (default) → ChromaDB local
    # "qdrant"             → Qdrant Cloud (GCP)
    # -----------------------------
	
    # Default configuration
    # VECTOR_DB_TYPE = os.getenv("VECTOR_DB_TYPE", "chromadb")

    VECTOR_DB_TYPE = os.getenv("VECTOR_DB_TYPE", "qdrant")

    # -----------------------------
    # Qdrant Cloud  (activo solo cuando VECTOR_DB_TYPE="qdrant")
    # -----------------------------
    QDRANT_URL     = os.getenv("QDRANT_URL", "")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

    # -----------------------------
    # HuggingFace Inference API
    # Reemplaza sentence-transformers local (PyTorch eliminado)
    # Modelo: sentence-transformers/all-MiniLM-L6-v2  →  384 dims
    # -----------------------------
    HF_API_KEY = os.getenv("HF_API_KEY", "")

    # -----------------------------
    # Configuración general
    # -----------------------------
    MAX_CONTEXT_LINES = 5
    DEBUG             = True


# Instancia global
Config = Settings()

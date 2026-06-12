# sync_rag.py

import os
import sys
from datetime import datetime

# ---------------------------------------------------------
# Asegurar que Python encuentre el proyecto completo
# ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from adapters.db.SQLiteAdapter import SQLiteAdapter
from adapters.rag.ChromaAdapter import ChromaAdapter   # ahora usa HTTP
from adapters.rag.EmbeddingAdapter import EmbeddingAdapter
from rag_indexer import RAGIndexer


def log(msg: str):
    """Imprime mensajes con timestamp."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def main():
    log("=== Hellen RAG Sync iniciado ===")
    log("Cargando componentes...")

    # ---------------------------------------------------------
    # Inicializar adaptadores
    # ---------------------------------------------------------
    try:
        db_path = os.path.join(BASE_DIR, "hellencommerce.db")

        db = SQLiteAdapter(db_path)

        # Cliente HTTP → estable en Windows
        rag = ChromaAdapter(
            collection_name="hellen_rag",
            host="localhost",
            port=8000
        )

        embedder = EmbeddingAdapter()

        log("Adaptadores cargados correctamente.")
    except Exception as e:
        log(f"ERROR al inicializar adaptadores: {e}")
        sys.exit(1)

    # ---------------------------------------------------------
    # Crear indexador
    # ---------------------------------------------------------
    indexer = RAGIndexer(db, rag, embedder)

    # ---------------------------------------------------------
    # Ejecutar sincronización
    # ---------------------------------------------------------
    try:
        log("Sincronizando registros desde SQLite hacia ChromaDB (HTTP)...")
        indexer.sync_all()
        log("Sincronización completada correctamente.")
    except Exception as e:
        log(f"ERROR durante la sincronización: {e}")
        sys.exit(1)

    log("=== Hellen RAG Sync finalizado ===")


if __name__ == "__main__":
    main()
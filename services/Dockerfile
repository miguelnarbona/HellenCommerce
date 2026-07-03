FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias para compilar librerías (ej. hnswlib para chromadb)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Variables por defecto (override vía docker-compose)
ENV LLM_MODE=online \
    HF_API_KEY="" \
    SERVICE_NAME="compra_service" \
    SERVICE_PORT="8014"

# Copiar e instalar dependencias unificadas
COPY services/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# Copiar el script de entrada y darle permisos de ejecución
COPY services/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Copiar todo el código de los servicios secundarios
COPY services/ /app/services/

# ENTRYPOINT para enrutar al servicio correcto
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

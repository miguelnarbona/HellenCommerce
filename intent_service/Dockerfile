FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Variables de entorno para pip
ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

ENV LLM_MODE=online \
    HF_API_KEY=""

LABEL org.opencontainers.image.source=https://github.com

# Copiar requirements primero (capa de caché eficiente)
COPY intent_service/requirements.txt .
RUN pip install -r requirements.txt
RUN python -m spacy download es_core_news_lg

# ==========================================
# 🚀 LA SOLUCIÓN LIMPIA: COPIAR TODO EL CONTENIDO
# ==========================================
# Copiamos absolutamente TODO lo que está dentro de la carpeta local hacia la raíz /app
COPY intent_service/ /app/

# Copiar carpetas compartidas globales del proyecto (si existen en la raíz del repositorio)
COPY app /app/app

EXPOSE 9010

CMD ["python", "-u", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9010"]

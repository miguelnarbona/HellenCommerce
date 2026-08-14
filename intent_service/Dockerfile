FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema mÃ­nimas para spacy/scipy (modo online no necesita llama-cpp)
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

# ConfiguraciÃ³n del servicio (override vÃ­a docker-compose)
ENV LLM_MODE=online \
    HF_API_KEY=""

LABEL org.opencontainers.image.source=https://github.com

# Copiar requirements primero (cache layer)
COPY requirements.txt .

RUN pip install -r requirements.txt

# Copiar el cÃ³digo del servicio
COPY intent_service/main.py /app/main.py
COPY intent_service/intent_semantic.py /app/intent_semantic.py
COPY intent_service/__init__.py /app/__init__.py

# Copiar carpetas compartidas del proyecto
COPY app /app/app

EXPOSE 9010

CMD ["python", "-u", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9010"]

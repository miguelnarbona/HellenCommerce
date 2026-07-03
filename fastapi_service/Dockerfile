FROM python:3.11-slim

WORKDIR /app

# Dependencias de sistema necesarias para psutil y compilaciÃ³n nativa mÃ­nima
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        build-essential \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Variables de entorno para pip y Python
ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# ConfiguraciÃ³n del servicio (override vÃ­a docker-compose)
ENV LLM_MODE=online \
    HF_API_KEY=""

# Copiar requirements primero (cache layer)
COPY fastapi_service/requirements.txt /app/requirements.txt

RUN pip install -r requirements.txt

# Copiar el cÃ³digo del servicio
COPY fastapi_service/main.py /app/main.py

# Copiar carpetas compartidas del proyecto
COPY app /app/app

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]

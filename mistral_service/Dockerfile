FROM python:3.11-slim

WORKDIR /app

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

LABEL org.opencontainers.image.source=https://github.com

# Copiar requirements primero (cache layer)
COPY requirements.txt /app/requirements.txt

RUN pip install -r requirements.txt

# Copiar el cÃ³digo del servicio
COPY mistral_service/main.py /app/main.py

# Copiar carpetas compartidas del proyecto
COPY app /app/app

EXPOSE 9001

CMD ["python", "-u", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9001"]

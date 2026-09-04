FROM python:3.11-slim

WORKDIR /app

ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Configuración del servicio (override vía docker-compose)
ENV LLM_MODE=online \
    HF_API_KEY=""

# 🛠️ CORREGIDO: Ahora apunta a tu repositorio exacto
LABEL org.opencontainers.image.source=https://github.com

# Copiar requirements primero (cache layer)
COPY logging_service/requirements.txt .

RUN pip install -r requirements.txt

# Copiar el código del servicio (explícito: sin __pycache__ ni archivos temporales)
COPY logging_service/main.py /app/main.py

# Copiar carpetas compartidas del proyecto
COPY app /app/app

EXPOSE 8099

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8099", "--log-level", "debug"]

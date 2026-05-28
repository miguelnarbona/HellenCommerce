FROM mirror.gcr.io/library/python:3.11-slim

WORKDIR /app

# Forzar IPv4 para evitar timeouts en redes inestables
RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4

# CORRECCIÓN CRÍTICA: Se movió la limpieza de caché (rm -rf) FUERA del bucle de reintentos.
# Si el primer intento fallaba a la mitad, borraba las listas y el segundo intento fallaba garantizado.
RUN for i in 1 2 3 4 5; do \
        apt-get update && \
        apt-get install -y --no-install-recommends \
            build-essential \
            curl \
            ca-certificates \
        && update-ca-certificates \
        && break || (echo "Reintentando apt en 10s..." && sleep 10); \
    done \
    && rm -rf /var/lib/apt/lists/*

# Variables de entorno globales para PIP (Centralizadas aquí en lugar de usar comandos 'pip config')
ENV PIP_DEFAULT_TIMEOUT=2000 \
    PIP_RETRIES=50 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=https://pypi.org/simple \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.txt /app/requirements.txt

# Instalar dependencias Python con reintentos (Simplificado gracias a las variables de entorno de arriba)
RUN for i in 1 2 3 4 5; do \
        pip install -r requirements.txt \
        && break || (echo "Reintentando pip en 10s..." && sleep 10); \
    done

COPY main.py /app/main.py

EXPOSE 8080

# Ejecución limpia usando el módulo uvicorn
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]

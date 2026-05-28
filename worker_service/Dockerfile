FROM mirror.gcr.io/library/python:3.11-slim

WORKDIR /app

# Forzar IPv4 para evitar timeouts en redes inestables
RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4

# CORRECCIÓN DE CACHÉ: Se movió la limpieza (rm -rf) FUERA del bucle de reintentos
RUN for i in 1 2 3 4 5; do \
        apt-get update && \
        apt-get install -y --no-install-recommends \
            build-essential \
            cmake \
            libopenblas-dev \
            libomp-dev \
            libssl-dev \
            libffi-dev \
            rustc \
            cargo \
        && break || (echo "Reintentando apt en 10s..." && sleep 10); \
    done \
    && rm -rf /var/lib/apt/lists/*

# Variables de entorno globales para PIP (Centralizadas y consolidadas)
ENV PIP_DEFAULT_TIMEOUT=2000 \
    PIP_RETRIES=50 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=https://pypi.org/simple \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# CORRECCIÓN: Ruta de origen desde la raíz del proyecto
COPY worker_service/requirements.txt /app/requirements.txt

# Instalar dependencias Python con reintentos
RUN for i in 1 2 3 4 5; do \
        pip install -r requirements.txt \
        && break || (echo "Reintentando pip en 10s..." && sleep 10); \
    done

# CORRECCIÓN: Copia de archivos desde las rutas reales del proyecto
COPY worker_service/main.py /app/main.py
COPY app /app/app
COPY app/config /app/config

# Documentación del puerto del servicio
EXPOSE 9000

# Comando de inicio optimizado (Se remueve el flag -u duplicado por PYTHONUNBUFFERED)
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000", "--workers", "1"]

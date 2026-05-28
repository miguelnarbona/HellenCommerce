# ==========================================
# ETAPA 1: Constructor (Build Stage)
# ==========================================
FROM mirror.gcr.io/library/python:3.11-slim AS builder

WORKDIR /app

RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4

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

# 🛠️ CORRECCIÓN: Se eliminó PIP_INDEX_URL para que use el mirror nativo de Google sin forzar PyPI
ENV PIP_DEFAULT_TIMEOUT=2000 \
    PIP_RETRIES=50 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY worker_service/requirements.txt .

# 🛠️ CORRECCIÓN: Aseguramos la instalación en la ruta que la Etapa 2 va a buscar
RUN for i in 1 2 3 4 5; do \
        pip install --user -r requirements.txt \
        && break || (echo "Reintentando pip en 10s..." && sleep 10); \
    done

# ==========================================
# ETAPA 2: Imagen Final de Producción (Runtime)
# ==========================================
FROM mirror.gcr.io/library/python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH=/root/.local/bin:$PATH

RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4 \
    && apt-get update && apt-get install -y --no-install-recommends \
        libopenblas-dev \
        libomp-dev \
    && rm -rf /var/lib/apt/lists/*

# Traer las dependencias compiladas de Python desde el builder
COPY --from=builder /root/.local /root/.local

# Copia los archivos del servicio desde la raíz del proyecto
COPY worker_service/main.py /app/main.py

# Copia las carpetas compartidas y vecinas
COPY app /app/app
COPY app/config /app/config

EXPOSE 9000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000", "--workers", "1"]

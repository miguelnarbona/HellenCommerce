# 🚀 INDICAMOS EL PUENTE DE LA RAÍZ AL INICIO DEL ARCHIVO
FROM project_root AS repo_source

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

ENV PIP_DEFAULT_TIMEOUT=2000 \
    PIP_RETRIES=50 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=https://pypi.org

COPY requirements.txt .

RUN for i in 1 2 3 4 5; do \
        pip install --user --no-cache-dir -r requirements.txt \
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

# Traer las dependencias compiladas de Python
COPY --from=builder /root/.local /root/.local

# Copiar archivos locales del propio worker_service
COPY main.py /app/main.py

# 💡 SOLUCIÓN REAL: Traemos las carpetas desde la etapa "repo_source" que definimos arriba
COPY --from=repo_source app /app/app
COPY --from=repo_source app/config /app/config

EXPOSE 9000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000", "--workers", "1"]

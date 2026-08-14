# ==========================================
# ETAPA 1: Constructor (Build Stage)
# ==========================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        libopenblas-dev \
        libomp-dev \
        libssl-dev \
        libffi-dev \
        rustc \
        cargo \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt ./requirements.txt

RUN pip install --user -r requirements.txt

# ==========================================
# ETAPA 2: Imagen Final de ProducciÃ³n (Runtime)
# ==========================================
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH=/root/.local/bin:$PATH \
    LLM_MODE=online \
    HF_API_KEY=""

LABEL org.opencontainers.image.source=https://github.com

# Bibliotecas de runtime para sentence-transformers/chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
        libopenblas-dev \
        libomp-dev \
    && rm -rf /var/lib/apt/lists/*

# Traer las dependencias compiladas desde el builder
COPY --from=builder /root/.local /root/.local

# Copiar el cÃ³digo del servicio y carpetas compartidas
COPY worker_service/main.py /app/main.py
COPY app /app/app

EXPOSE 9000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000", "--workers", "1"]

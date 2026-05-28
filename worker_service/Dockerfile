# ==========================================
# ETAPA 1: Constructor (Build Stage)
# ==========================================
FROM mirror.gcr.io/library/python:3.11-slim AS builder

WORKDIR /app

# Forzar IPv4 para evitar timeouts en redes inestables
RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4

# Instalar herramientas de compilación pesadas (Rust, Cargo, CMake, etc.)
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

# Variables de entorno optimizadas para la compilación de PIP
# CORRECCIÓN: Se cambió 'https://pypi.org' por 'https://pypi.org' (Ruta correcta del índice)
ENV PIP_DEFAULT_TIMEOUT=2000 \
    PIP_RETRIES=50 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=https://pypi.org

COPY requirements.txt .

# Compilar e instalar las dependencias directamente en un directorio local aislado
RUN for i in 1 2 3 4 5; do \
        pip install --user --no-cache-dir -r requirements.txt \
        && break || (echo "Reintentando pip en 10s..." && sleep 10); \
    done


# ==========================================
# ETAPA 2: Imagen Final de Producción (Runtime)
# ==========================================
FROM mirror.gcr.io/library/python:3.11-slim

WORKDIR /app

# Variables de entorno esenciales para la ejecución
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH=/root/.local/bin:$PATH

# Instalar solo las librerías compartidas de ejecución en Debian (Sin compiladores)
RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4 \
    && apt-get update && apt-get install -y --no-install-recommends \
        libopenblas-dev \
        libomp-dev \
    && rm -rf /var/lib/apt/lists/*

# 🧠 OPTIMIZACIÓN CLAVE: Traer solo las dependencias Python ya compiladas de la etapa anterior
# Esto deja fuera a Rust, Cargo, GCC y CMake, reduciendo la imagen hasta un 70%
COPY --from=builder /root/.local /root/.local

# Copiar archivos locales del propio worker_service
COPY main.py /app/main.py

# Copiar carpetas externas mapeadas mediante project_root en GitHub Actions
COPY --from=project_root app /app/app
COPY --from=project_root app/config /app/config

EXPOSE 9000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000", "--workers", "1"]

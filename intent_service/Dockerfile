FROM mirror.gcr.io/library/python:3.11-slim

WORKDIR /app

# Forzar IPv4 para evitar timeouts en redes inestables
RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4

# Instalar dependencias del sistema con reintentos
RUN for i in 1 2 3 4 5; do \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && break || sleep 10; \
done

# Configuración de pip
RUN pip config set global.index-url https://pypi.org/simple
RUN pip config set global.timeout 300
RUN pip config set global.retries 10

COPY requirements.txt /app/requirements.txt

ENV PIP_DEFAULT_TIMEOUT=2000
ENV PIP_RETRIES=50
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar dependencias Python con reintentos
RUN for i in 1 2 3 4 5; do \
    pip install --default-timeout=2000 --retries=50 --no-cache-dir -r requirements.txt \
    && break || sleep 10; \
done

# Copiar el servicio de intención
COPY intent_service.py /app/intent_service.py

# Copiar el modelo (opcional, si lo empaquetas dentro del contenedor)
# COPY models/qwen2.5-1.5b-instruct-q4_k_m.gguf /app/models/

EXPOSE 9010

# Ejecutar el servicio con Uvicorn
CMD ["python", "-u", "-m", "uvicorn", "intent_service:app", "--host", "0.0.0.0", "--port", "9010"]

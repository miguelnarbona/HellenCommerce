FROM mirror.gcr.io/library/python:3.11-slim

WORKDIR /app

# Forzar IPv4 para evitar timeouts en redes inestables
RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4

# Cambiar mirrors a uno más estable (USA)
# RUN sed -i 's|deb.debian.org|ftp.us.debian.org|g' /etc/apt/sources.list

# Instalar dependencias del sistema con reintentos (llama.cpp necesita build-essential)
RUN for i in 1 2 3 4 5; do \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
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

COPY main.py /app/main.py

# El modelo se montará como volumen en /models
ENV MODEL_PATH=/models/mistral/phi-2-instruct.Q4_K_S/phi-2-instruct.Q4_K_S.gguf
ENV N_CTX=1024
ENV N_THREADS=6

EXPOSE 9001

CMD ["python", "-u", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9001"]

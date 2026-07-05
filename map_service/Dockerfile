FROM mirror.gcr.io/library/python:3.11-slim

# Evitar bytecode y buffering
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

LABEL org.opencontainers.image.source=https://github.com

# Instalar dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar
COPY requirements.txt .

ENV PIP_DEFAULT_TIMEOUT=2000
ENV PIP_RETRIES=50
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --default-timeout=2000 --retries=50 --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Puerto interno de FastAPI
EXPOSE 5000

# Comando de arranque
CMD ["python", "-u", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]

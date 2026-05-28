FROM python:3.11-slim
WORKDIR /app

# 1. Instalar herramientas necesarias para compilar llama-cpp-python
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# 2. Copiar e instalar las dependencias de Python
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# (Opcional) Si en producción copias el código de tu app, descomenta esto:
# COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8014"]

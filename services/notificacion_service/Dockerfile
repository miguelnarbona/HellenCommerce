FROM python:3.11-slim

WORKDIR /app

# FORZAR CAMBIO: Instalar compiladores C++ nativos obligatorios
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# El codigo se monta via volumen en desarrollo.
# En produccion se copia aqui:
# COPY notificacion_service/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8016"]

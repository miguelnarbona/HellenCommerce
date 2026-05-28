FROM python:3.11-slim

WORKDIR /app

# Copiar requirements del servicio (contexto = raiz del proyecto)
COPY saludo_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# El codigo se monta via volumen en desarrollo.
# En produccion se copia aqui:
# COPY saludo_service/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8018"]

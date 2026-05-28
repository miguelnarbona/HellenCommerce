FROM python:3.11-slim

WORKDIR /app

# CORRECCIÓN 1: Como el contexto es la carpeta del servicio, el archivo está en la raíz
COPY requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

# CORRECCIÓN 2: DESCOMENTADO PARA PRODUCCIÓN. 
# Copia todo el código del servicio dentro del contenedor para que viaje a GHCR e ir a Oracle
COPY . .

# Exponer el puerto correcto para control y documentación
EXPOSE 8099

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8099"]

#!/bin/sh
# ============================================================
# Entrypoint unificado para servicios secundarios de HellenCommerce
# Usa las variables de entorno SERVICE_NAME y SERVICE_PORT
# para arrancar el servicio correcto desde la imagen compartida.
# ============================================================
set -e

SERVICE_NAME="${SERVICE_NAME:-compra_service}"
SERVICE_PORT="${SERVICE_PORT:-8014}"

echo ">>> Arrancando servicio: $SERVICE_NAME en puerto $SERVICE_PORT"
echo ">>> LLM_MODE: ${LLM_MODE:-online}"

exec python -m uvicorn "services.${SERVICE_NAME}.main:app" \
    --host 0.0.0.0 \
    --port "$SERVICE_PORT" \
    --workers 1

#!/bin/sh
# ============================================================
# Entrypoint unificado para servicios secundarios de HellenCommerce
# Usa las variables de entorno SERVICE_NAME y SERVICE_PORT
# para arrancar el servicio correcto desde la imagen compartida.
# ============================================================
set -e

# 1. Capturar el nombre del servicio (por defecto compra_service)
SERVICE_NAME="${SERVICE_NAME:-compra_service}"

# 2. Mapeo automático de puertos si SERVICE_PORT no fue definido explícitamente
if [ -z "$SERVICE_PORT" ]; then
    case "$SERVICE_NAME" in
        "registro_service")     SERVICE_PORT="8010" ;;
        "contacto_service")     SERVICE_PORT="8011" ;;
        "mensajeria_service")   SERVICE_PORT="8012" ;;
        "venta_service")        SERVICE_PORT="8013" ;;
        "compra_service")       SERVICE_PORT="8014" ;;
        "informativa_service")  SERVICE_PORT="8015" ;;
        "notificacion_service") SERVICE_PORT="8016" ;;
        "transporte_service")   SERVICE_PORT="8017" ;;
        "saludo_service")       SERVICE_PORT="8018" ;;
        "despedida_service")    SERVICE_PORT="8019" ;;
        "ruta_service")         SERVICE_PORT="8020" ;;
        "negocio_service")      SERVICE_PORT="8021" ;;
        "servicio_service")     SERVICE_PORT="8022" ;;
        "otra_service")         SERVICE_PORT="8023" ;;
        *)
            echo "⚠️ ADVERTENCIA: Servicio desconocido '$SERVICE_NAME'. Usando puerto por defecto 8014."
            SERVICE_PORT="8014"
            ;;
    esac
fi

echo "========================================================="
echo ">>> HellenCommerce Orchestrator"
echo ">>> Arrancando servicio : $SERVICE_NAME"
echo ">>> Puerto asignado     : $SERVICE_PORT"
echo ">>> LLM_MODE            : ${LLM_MODE:-online}"
echo "========================================================="

# 3. Ejecución del proceso reemplazando el hilo del shell (exec)
exec python -m uvicorn "services.${SERVICE_NAME}.main:app" \
    --host 0.0.0.0 \
    --port "$SERVICE_PORT" \
    --workers 1

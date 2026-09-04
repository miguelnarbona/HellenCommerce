#!/bin/sh
# ============================================================
# Entrypoint unificado para servicios secundarios de HellenCommerce
# Usa las variables de entorno SERVICE_NAME y SERVICE_PORT
# para arrancar el servicio correcto desde la imagen compartida.
# ============================================================
set -e

# 1. Capturar el nombre del servicio (por defecto compra_service)
SERVICE_NAME="${SERVICE_NAME:-bunker_compra_service}"

# 2. Mapeo automático de puertos si SERVICE_PORT no fue definido explícitamente
if [ -z "$SERVICE_PORT" ]; then
    case "$SERVICE_NAME" in
        "bunker_registro_service")     SERVICE_PORT="8010" ;;
        "bunker_contacto_service")     SERVICE_PORT="8011" ;;
        "bunker_mensajeria_service")   SERVICE_PORT="8012" ;;
        "bunker_venta_service")        SERVICE_PORT="8013" ;;
        "bunker_compra_service")       SERVICE_PORT="8014" ;;
        "bunker_informativa_service")  SERVICE_PORT="8015" ;;
        "bunker_notificacion_service") SERVICE_PORT="8016" ;;
        "bunker_transporte_service")   SERVICE_PORT="8017" ;;
        "bunker_saludo_service")       SERVICE_PORT="8018" ;;
        "bunker_despedida_service")    SERVICE_PORT="8019" ;;
        "bunker_ruta_service")         SERVICE_PORT="8020" ;;
        "bunker_negocio_service")      SERVICE_PORT="8021" ;;
        "bunker_servicio_service")     SERVICE_PORT="8022" ;;
        "bunker_otra_service")         SERVICE_PORT="8023" ;;
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
    --workers 1 \
    --log-level "debug"

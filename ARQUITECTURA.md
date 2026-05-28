# HellenCommerce 2.0.1 - Arquitectura de Microservicios

## 📋 Visión General

HellenCommerce 2.0.1 es una plataforma de comercio inteligente basada en microservicios asíncronos, con un **Orquestador central como librería interna** (NO microservicio) que coordina todas las interacciones.

## 🏗️ Arquitectura

### Principios de Diseño

1. **Orquestador como Librería Interna**: El `Orchestrator` es importado directamente por `fastapi_service`, eliminando latencia de red
2. **Comunicación Asíncrona**: Todas las operaciones son no bloqueantes usando `asyncio` y `FastAPI`
3. **Fan-out/Fan-in Paralelo**: Múltiples intenciones se procesan concurrentemente
4. **Self-Healing**: Sistema de logs inteligente con aprobación humana para hot-fixes
5. **Aislamiento de Dominios**: Cada microservicio tiene responsabilidades claramente delimitadas

### Flujo de Datos

```
┌─────────────┐    WebSocket    ┌──────────────────┐
│   AppWeb    │◄──────────────►│  FastAPI Ingress │
└─────────────┘                 └────────┬─────────┘
                                         │
                                         │ Importa directamente
                                         ▼
                                  ┌──────────────┐
                                  │ Orchestrator │
                                  │  (Librería)  │
                                  └──────┬───────┘
                                         │
                 ┌───────────────────────┼───────────────────────┐
                 │                       │                       │
          ┌──────▼──────┐         ┌──────▼──────┐        ┌──────▼──────┐
          │   Intent    │         │   Worker    │        │  Mistral    │
          │  Service    │         │  Service    │        │  Service    │
          └─────────────┘         └──────┬──────┘        └──────┬──────┘
                                         │                       │
                                         │  Fan-out              │
                                         ▼                       │
                    ┌────────────────────────────────┐          │
                    │   Servicios Especializados     │          │
                    │  ┌──────────────────────────┐  │          │
                    │  │ COMPRA  VENTA  RUTA ...  │  │          │
                    │  └──────────────────────────┘  │          │
                    └────────────────────────────────┘          │
                                         │                       │
                                         └───────────┬───────────┘
                                                     │
                                                     ▼
                                            ┌──────────────┐
                                            │  Unificación │
                                            │  Mistral     │
                                            └──────┬───────┘
                                                   │
                                                   ▼
                                            ┌──────────────┐
                                            │  Persistir   │
                                            │ SQLite/Chroma│
                                            └──────────────┘
```

## 📁 Estructura del Proyecto

```
HellenCommerce-2.0.1/
├── app/
│   ├── core/
│   │   └── orchestrator/           # Orquestador como librería interna
│   │       ├── __init__.py
│   │       ├── orchestrator.py     # Coordinador principal
│   │       ├── intent_detector.py  # Detección de intenciones
│   │       ├── prompt_builder.py   # Construcción de prompts
│   │       ├── specialized_dispatcher.py  # Fan-out a servicios
│   │       ├── response_unifier.py # Unificación de respuestas
│   │       └── logging_client.py   # Cliente de logging
│   ├── shared/                     # Librerías compartidas
│   ├── data/                       # Base de datos SQLite
│   ├── models/                     # Modelos GGUF
│   ├── prompts/                    # Templates de prompts
│   └── resources/                  # Keywords y recursos
│
├── fastapi_service/                # Punto de entrada único
│   ├── main.py                     # Importa Orchestrator
│   ├── requirements.txt
│   └── Dockerfile
│
├── services/                       # Microservicios especializados
│   ├── registro_service/
│   ├── contacto_service/
│   ├── mensajeria_service/
│   ├── venta_service/
│   ├── compra_service/
│   ├── informativa_service/
│   ├── notificacion_service/
│   ├── transporte_service/
│   ├── saludo_service/
│   ├── despedida_service/
│   ├── ruta_service/
│   ├── negocio_service/
│   ├── servicio_service/
│   └── otra_service/
│
├── intent_service/                 # Detección de intenciones
├── worker_service/                 # Generador de prompts
├── mistral_service/                # Unificador de respuestas
├── logging_service/                # Subsistema de Logs + Self-Healing
├── admin_dashboard/                # Panel de administración
│
├── docker-compose.yml              # Orquestación de contenedores
└── ARQUITECTURA.md                 # Este archivo
```

## 🔧 Microservicios

### Servicios de Infraestructura

| Servicio | Puerto | Función |
|----------|--------|---------|
| `fastapi_service` | 8000 | Punto de entrada WebSocket/HTTP |
| `intent_service` | 8002 | Detección de intenciones con LLM |
| `worker_service` | 8003 | Construcción de prompts personalizados |
| `mistral_service` | 8004 | Unificación de respuestas multi-intención |
| `logging_service` | 8099 | Subsistema de logs y self-healing |
| `admin_dashboard` | 3000 | Panel de administración |

### Servicios Especializados por Categoría

| Servicio | Puerto | Intención |
|----------|--------|-----------|
| `registro_service` | 8010 | REGISTRO |
| `contacto_service` | 8011 | CONTACTO |
| `mensajeria_service` | 8012 | MENSAJERIA |
| `venta_service` | 8013 | VENTA |
| `compra_service` | 8014 | COMPRA |
| `informativa_service` | 8015 | INFORMATIVA |
| `notificacion_service` | 8016 | NOTIFICACION |
| `transporte_service` | 8017 | TRANSPORTE |
| `saludo_service` | 8018 | SALUDO |
| `despedida_service` | 8019 | DESPEDIDA |
| `ruta_service` | 8020 | RUTA |
| `negocio_service` | 8021 | NEGOCIO |
| `servicio_service` | 8022 | SERVICIO |
| `otra_service` | 8023 | OTRA |

## 🚀 Despliegue

### Requisitos

- Docker y Docker Compose
- Python 3.11+ (para desarrollo local)
- Modelos GGUF en `app/models/`

### Inicio Rápido

```bash
# Clonar o copiar el proyecto
cd HellenCommerce-2.0.1

# Configurar variables de entorno (opcional)
cp .env.example .env
# Editar .env con las claves API necesarias

# Iniciar todos los servicios
docker-compose up -d

# Ver logs
docker-compose logs -f

# Detener
docker-compose down
```

### Verificación

```bash
# Health check
curl http://localhost:8000/health

# Probar WebSocket (usar wscat o cliente WebSocket)
wscat -c ws://localhost:8000/ws/user123
```

## 🔒 Seguridad

- Autenticación Firebase en endpoints críticos
- CORS configurado para orígenes específicos
- Variables de entorno para credenciales sensibles
- Aislamiento de red entre contenedores

## 📊 Monitoreo

### Logs

Todos los servicios envían logs al `logging_service` vía WebSocket:

```json
{
  "timestamp": "2026-05-24T10:00:00",
  "log_level": "ERROR",
  "service_origin": "venta_service",
  "source_file": "main.py",
  "line_number": 42,
  "error_description": "Timeout en consulta DB",
  "proposed_solution": "Aumentar timeout o optimizar query",
  "status_flag": "PENDIENTE"
}
```

### Admin Dashboard

Acceder a `http://localhost:3000` para:
- Ver logs en tiempo real
- Aprobar/rechazar hot-fixes propuestos por IA
- Monitorear salud del sistema

## 🔮 Integraciones Futuras (Modo Desarrollo)

### n8n y Claude

El orquestador incluye hooks para integración con n8n y Claude:

```python
# En .env:
N8N_WEBHOOK_URL=https://n8n.example.com/webhook/hellen
CLAUDE_WEBHOOK_URL=https://api.anthropic.com/v1/messages

# El orchestrator envía eventos asíncronamente:
asyncio.create_task(self._trigger_external_pipeline(ctx))
```

## 📝 Notas de Migración desde 2.0.0

### Cambios Principales

1. **Orchestrator como librería**: Ya no es un microservicio separado
2. **Comunicación directa**: `fastapi_service` importa `Orchestrator` directamente
3. **Menor latencia**: Eliminadas llamadas HTTP internas innecesarias
4. **Self-healing mejorado**: Sistema de logs con aprobación humana

### Preservación de Lógica

El 100% de la lógica de negocio existente se mantiene intacta. Solo cambian:
- Convenciones de nombres
- Estructura de comunicación
- Archivos de configuración

## 📄 Licencia

Propietario - HellenCommerce
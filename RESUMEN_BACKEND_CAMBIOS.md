# 📋 Resumen de Cambios en el Backend — HellenCommerce

> **Periodo analizado:** últimos 10 commits (rama `main`)
> **Fecha del análisis:** 2026-09-04
> **Total archivos modificados (backend):** 23
> **Total cambios:** +141 / −71 líneas

---

## 🎯 Objetivo general de los cambios

El foco estuvo en **estabilizar el flujo orquestador ↔ microservicios** y en **armonizar nombres/URLs** para que el enrutamiento entre `bunker_intent_service`, `bunker_mistral_service`, `bunker_worker_service` y los servicios de negocio (saludo, venta, registro, etc.) funcione de forma consistente tanto en local (`127.0.0.1`) como dentro de Docker.

---

## 🔧 Detalle por commit (orden cronológico inverso)

### 1. `a38564c` — fix: pdandict error 422
Corregido error 422 tipo `pdandict` al construir el prompt.
- `app/core/orchestrator/prompt_builder.py`
- `worker_service/main.py`

### 2. `91fe997` — fix: worker service error :422
Corrección del error 422 devuelto por `bunker_worker_service` (validación Pydantic / payload mal formado).
- `worker_service/main.py`

### 3. `b151fbf` — fix: Mistral tracking
Ajustes al *tracking* del microservicio Mistral (idempotencia / correlación de peticiones).
- `mistral_service/main.py`

### 4. `2b0f0a6` — fix: error unificando respuesta
Solución de errores durante la fase de unificación de respuestas del orquestador.
- `app/core/orchestrator/response_unifier.py`

### 5. `9ee6ebc` — fix: cambiar nombre a `bunker_` de todos los servicios
Renombrado masivo para prefijar todos los servicios con `bunker_` (estandarización de la red Docker).
- `fastapi_service/main.py`
- `intent_service/main.py`
- `mistral_service/main.py`
- `services/compra_service/main.py`
- `services/contacto_service/main.py`
- `services/despedida_service/main.py`
- `services/informativa_service/main.py`
- `services/mensajeria_service/main.py`
- `services/negocio_service/main.py`
- `services/notificacion_service/main.py`
- `services/otra_service/main.py`
- `services/registro_service/main.py`
- `services/ruta_service/main.py`
- `services/saludo_service/main.py`
- `services/servicio_service/main.py`
- `services/transporte_service/main.py`
- `services/venta_service/main.py`
- `worker_service/main.py`

### 6. `73702c0` — fix: cambiar nombre a `bunker_intent_service`
- `app/core/orchestrator/intent_detector.py`

### 7. `2f81444` — Reparar nombre `intent_service`
- `app/core/orchestrator/intent_detector.py`

### 8. `26c9530` — Reparar fastapi context.manager
Reparación del ciclo de vida del contexto en FastAPI (startup/shutdown, inyección de dependencias).
- `app/context/ContextManager.py`

### 9. `33742bf` — Reparar URL de los servicios, sustituirlos por `127.0.0.1`
Migración de los hostnames internos a `127.0.0.1` para entornos locales.
- `app/core/orchestrator/intent_detector.py`
- `docker-compose.yml`
- `fastapi_service/main.py`
- `intent_service/main.py`
- `mistral_service/main.py`
- `services/contacto_service/main.py`
- `services/despedida_service/main.py`
- `services/informativa_service/main.py`
- `services/mensajeria_service/main.py`
- `services/negocio_service/main.py`
- `services/notificacion_service/main.py`
- `services/otra_service/main.py`
- `services/registro_service/main.py`
- `services/ruta_service/main.py`
- `services/saludo_service/main.py`
- `services/servicio_service/main.py`
- `services/transporte_service/main.py`
- `services/venta_service/main.py`
- `worker_service/main.py`

### 10. `4311e31` — Reparar url worker_service
Ajuste específico de la URL del `worker_service`.
- `worker_service/main.py`

---

## 📂 Archivos del backend modificados (consolidado)

### 🧠 Núcleo de orquestación (`app/`)
| Archivo | Rol |
|---|---|
| `app/context/ContextManager.py` | Ciclo de vida del contexto global de la app. |
| `app/core/orchestrator/intent_detector.py` | Detección de intención + nombres de servicios. |
| `app/core/orchestrator/prompt_builder.py` | Construcción del prompt al LLM. |
| `app/core/orchestrator/response_unifier.py` | Unificación de respuesta final. |

### 🤖 Servicios de IA / coordinación
| Archivo | Rol |
|---|---|
| `fastapi_service/main.py` | API principal (FastAPI). |
| `intent_service/main.py` | Microservicio `bunker_intent_service`. |
| `mistral_service/main.py` | Microservicio Mistral + tracking. |
| `worker_service/main.py` | Worker orquestador + fix 422. |

### 🛒 Microservicios de negocio (`services/`)
- `services/compra_service/main.py`
- `services/contacto_service/main.py`
- `services/despedida_service/main.py`
- `services/informativa_service/main.py`
- `services/mensajeria_service/main.py`
- `services/negocio_service/main.py`
- `services/notificacion_service/main.py`
- `services/otra_service/main.py`
- `services/registro_service/main.py`
- `services/ruta_service/main.py`
- `services/saludo_service/main.py`
- `services/servicio_service/main.py`
- `services/transporte_service/main.py`
- `services/venta_service/main.py`

### 🐳 Infra
- `docker-compose.yml` — renombrado de servicios a `bunker_*` y migración de hosts a `127.0.0.1`.

---

## 🧭 Resumen temático

| Tema | Commits | Archivos clave |
|---|---|---|
| **Errores 422 (pdandict / Pydantic)** | `a38564c`, `91fe997` | `prompt_builder.py`, `worker_service/main.py` |
| **Tracking Mistral** | `b151fbf` | `mistral_service/main.py` |
| **Unificación de respuesta** | `2b0f0a6` | `response_unifier.py` |
| **Renombrado a `bunker_*`** | `9ee6ebc`, `73702c0`, `2f81444` | `intent_detector.py`, todos los `main.py` |
| **Reparar URLs (`127.0.0.1`)** | `33742bf`, `4311e31` | `docker-compose.yml`, `worker_service/main.py`, todos los `main.py` |
| **Ciclo de vida FastAPI** | `26c9530` | `ContextManager.py` |

---

## ✅ Resultado neto

- **23 archivos backend modificados.**
- Red Docker homogeneizada con prefijo `bunker_`.
- Endpoints apuntan a `127.0.0.1` para desarrollo local.
- Errores 422 corregidos en el flujo `prompt_builder → worker → servicios`.
- Tracking Mistral estabilizado y unificador de respuestas funcional.

---

## 📁 Archivo generado

`C:\HellenCommerce\RESUMEN_BACKEND_CAMBIOS.md`
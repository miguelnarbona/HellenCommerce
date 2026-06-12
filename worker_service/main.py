import asyncio
import sys

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from app.builder.AppBuilder import AppBuilder
from contextlib import asynccontextmanager
import re

app = FastAPI()

# -----------------------------------------------------------
# Inicialización del Cosntructor del sistema IA (solo una vez)
# -----------------------------------------------------------
builder = AppBuilder()

# Cargar modelos, embeddings y notificaciones
builder.load_embeddings()
notification_manager = builder.notification_manager

# El Constructor del sistema le entrego todo al Director (Construido en el paso 12).
director = builder.get_director()

# -----------------------------------------------------------
# Estado inicial del producto
# -----------------------------------------------------------
def estado_inicial():
    return {
        "producto": None,
        "modelo": None,
        "color": None,
        "ubicacion": None,
        "marca": None,
        "precio_min": None,
        "precio_max": None,
        "extras": []
    }

# -----------------------------------------------------------
# Actualizar estado del producto
# -----------------------------------------------------------
def actualizar_estado_producto(state, message):
    if state is None:
        state = estado_inicial()

    # Asegurar que extras exista
    if state.get("extras") is None:
        state["extras"] = []

    msg = message.lower()

    # Producto
    if any(w in msg for w in ["ventilador", "cargador", "bocina", "tv", "telefono"]):
        state["producto"] = message
        return state

    # Modelo
    modelo = re.search(r"[a-zA-Z]{1,4}\d{1,4}", message)
    if modelo:
        state["modelo"] = modelo.group(0)
        return state

    # Color
    colores = ["rojo", "azul", "negro", "blanco", "verde"]
    for c in colores:
        if c in msg:
            state["color"] = c
            return state

    # Ubicación
    ubicaciones = ["holguin", "holguín", "habana", "santiago", "camaguey", "matanzas"]
    for u in ubicaciones:
        if u in msg:
            state["ubicacion"] = u
            return state

    # Precio
    precio = re.search(r"(\d+)\s*(usd|cup|pesos)?", msg)
    if precio:
        state["precio_max"] = precio.group(1)
        return state

    # Extras
    state["extras"].append(message)

    return state

# -----------------------------------------------------------
# Construir query de búsqueda
# -----------------------------------------------------------
def construir_query(state):
    partes = []

    if state["producto"]:
        partes.append(state["producto"])
    if state["modelo"]:
        partes.append(state["modelo"])
    if state["color"]:
        partes.append(state["color"])
    if state["ubicacion"]:
        partes.append(state["ubicacion"])
    if state["marca"]:
        partes.append(state["marca"])

    partes.extend(state["extras"])

    return " ".join(partes).strip()


# COPILOT-change: Agregar guardado automático de contexto en /infer para mantener coherencia conversacional
@app.post("/user/{user_id}/infer")
async def infer(user_id: str, payload: dict):
    message = payload["message"]

    try:
        # El Director toma todo la informacion que el Constructor le trajo y se la ordena
        # a la secretaria hacer un request (process_request)
        datos = await director.process_request(user_id, message)
        
        # COPILOT-add: Guardar contexto automáticamente para evitar pérdida de historial
        if "response" in datos and datos["response"]:
            builder.ctx.save_context(
                user_id,
                f"USUARIO: {message}",
                f"IA: {datos['response']}",
                tipo=datos.get("rol", "comprador")
            )
        
        return {"response": datos}

    except Exception as e:
        print(">>> ERROR en worker:", e, flush=True)
        return {"response": {}}

# -----------------------------------------------------------
# Guardar contexto (NO usa product_state)
# -----------------------------------------------------------
# @app.post("/context/save")
# def save_context(payload: dict):
#     user_id = payload["user_id"]
#     user_message = payload["user_message"]
#     ai_message = payload["ai_message"]

#     try:
#        builder.ctx.save_context(
#            user_id,
#            f"USUARIO: {user_message}",
#            f"IA: {ai_message}"
#        )
#        return {"status": "ok"}
#     except Exception as e:
#         print(">>> ERROR guardando contexto:", e, flush=True)
#         return {"status": "error", "detail": str(e)}


@app.post("/user/{user_id}/transporte/solicitar")
def solicitar_transporte(user_id: str, payload: dict):
    try:
        payload["user_id"] = user_id
        respuesta = builder.business_logic.procesar_solicitud_transporte(payload)
        return respuesta
    except Exception as e:
        print(">>> ERROR en procesar_solicitud_transporte:", e, flush=True)
        return {"success": False, "message": "Error interno en transporte"}


@app.post("/user/{user_id}/notificacion/{notif_id}/leida")
def marcar_leida(user_id: str, notif_id: int):
    notification_manager.marcar_leida(notif_id)
    return {"status": "ok", "notif_id": notif_id, "user_id": user_id}


@app.get("/health")
def health():
    return {"status": "ok"}

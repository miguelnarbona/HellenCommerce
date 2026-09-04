import asyncio
import os
import sys
import json
import datetime
import websockets
import platform

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from app.builder.AppBuilder import AppBuilder

# Importamos las dependencias compartidas (simuladas aquí, deben estar en /app/ en el contenedor)
system = platform.system()   
sys.path.append("c:/HellenCommerce") if system == "Windows" else sys.path.append("/app")
from app.utils.paths import hc_path, data_path
LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://bunker_logging_service:8099/ws/logs")

worker_model = None
builder = None
director = None

class PromptRequest(BaseModel):
    user_id: str
    message: str
    intents: list[str]
    # `contexto` puede llegar como:
    #   - dict  (formato esperado por el worker)
    #   - list  (historial conversacional plano, frecuente desde el orquestador)
    #   - None  (sin contexto previo)
    # Aceptar las 3 formas evita falsos 422 cuando cambia la representación
    # del historial entre el orquestador (Room/fastapi_service) y worker_service.
    contexto: dict | list | None = None

# ============================================================
# LOGGING AL LOGGING_SERVICE
# ============================================================
async def log_to_logging_service(level: str, msg: str, status_flag="SOLUCIONADO", line_num=0):
    try:
        async with websockets.connect(LOGGING_WS_URL) as ws:
            payload = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "log_level": level,
                "service_origin": "worker_service",
                "source_file": "main.py",
                "line_number": line_num,
                "file_path": __file__,
                "code_snippet": msg,
                "error_description": msg if level in ["ERROR", "WARNING"] else "",
                "proposed_solution": "",
                "status_flag": status_flag
            }
            await ws.send(json.dumps(payload))
    except Exception as e:
        print(f"[DEBUG] Error enviando log (worker_service): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global builder, director
    await log_to_logging_service("INFO", "Bootstrapping worker_service: Inicializando AppBuilder y Director", line_num=47)
    
    try:
        # Inicialización del constructor y director (preservando lógica existente)
        builder = AppBuilder()
        builder.load_embeddings()
        director = builder.get_director()
        await log_to_logging_service("INFO", "Worker Service: AppBuilder inicializado con éxito", line_num=54)
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al inicializar AppBuilder: {e}", line_num=56)

    # El modelo de prompts GGUF si aplica (por ahora mantenemos el flujo original de PromptBuilder basado en texto/archivos)
    model_path = os.getenv("WORKER_MODEL_PATH", "/app/models/prompt_generator.gguf")
    print(f"Cargando modelo generador de prompts (opcional, si hay GGUF local para optimizar prompts): {model_path}")
    
    yield
    print("Worker Service apagándose")

app = FastAPI(title="Worker Service - Prompt Generator", lifespan=lifespan)

@app.post("/prompt")
async def generate_prompts(req: PromptRequest):
    prompts_map = {}
    
    try:
        # Utilizamos la lógica de AppBuilder para construir los prompts basados en las intenciones
        # Simulamos que el director puede construir los prompts especializados sin ejecutar la inferencia aún
        
        # `contexto` puede llegar como dict (preferido), list (historial
        # plano) o None. Lo unificamos siempre a un dict para que el resto
        # del worker pueda tratarlo de forma homogénea.
        raw_contexto = req.contexto
        if raw_contexto is None:
            contexto_data = {}
        elif isinstance(raw_contexto, dict):
            contexto_data = raw_contexto
        elif isinstance(raw_contexto, list):
            contexto_data = {"history": raw_contexto, "raw": raw_contexto}
        else:
            contexto_data = {"raw": raw_contexto}
        
        # Iteramos sobre las intenciones detectadas para generar un prompt individual por cada una
        for intent in req.intents:
            # Aquí inyectamos la lógica del PromptBuilder de la AppBuilder heredada
            # Para este ejemplo y migración, simulamos la llamada al builder
            
            prompt_construido = ""
            
            # TODO: Adaptar director.process_request o builder.build() para que devuelva solo el prompt
            # (En la lógica original, process_request ejecutaba el LLM. Aquí la dividimos)
            
            # Mock / Adaptación temporal hasta que se ajuste el Director para devolver solo prompts
            if intent == "COMPRA":
                prompt_construido = builder.prompt_builder.with_var("message", req.message).with_roles("comprador", "broker").build()
            elif intent == "VENTA":
                prompt_construido = builder.prompt_builder.with_var("message", req.message).with_roles("vendedor", "broker").build()
            else:
                prompt_construido = f"Prompt genérico para intención {intent} con mensaje: {req.message}"
            
            prompts_map[intent] = prompt_construido
            
        await log_to_logging_service("INFO", f"Prompts generados para {req.user_id} intenciones: {req.intents}", line_num=96)
        
    except Exception as e:
        await log_to_logging_service("ERROR", f"Error generando prompts para {req.user_id}: {e}", line_num=99)
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"user_id": req.user_id, "prompts": prompts_map}

# Preservamos los endpoints auxiliares que estaban en el worker_service original
@app.post("/user/{user_id}/transporte/solicitar")
def solicitar_transporte(user_id: str, payload: dict):
    try:
        payload["user_id"] = user_id
        respuesta = builder.business_logic.procesar_solicitud_transporte(payload)
        return respuesta
    except Exception as e:
        asyncio.create_task(log_to_logging_service("ERROR", f"Error en transporte: {e}", line_num=111))
        return {"success": False, "message": "Error interno en transporte"}

@app.post("/user/{user_id}/notificacion/{notif_id}/leida")
def marcar_leida(user_id: str, notif_id: int):
    try:
        builder.notification_manager.marcar_leida(notif_id)
        return {"status": "ok", "notif_id": notif_id, "user_id": user_id}
    except Exception as e:
        asyncio.create_task(log_to_logging_service("ERROR", f"Error al marcar notificación: {e}", line_num=120))
        raise HTTPException(status_code=500, detail="Error interno")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    # 🚀 Esto obligará a Docker a pintar el JSON erróneo en la terminal
    print(f"❌ ¡ERROR 422 DETECTADO! Detalles de la validación: {exc.errors()}", flush=True)
    print(f"📦 Cuerpo del JSON recibido: {await request.body()}", flush=True)
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

@app.get("/health")
def health():
    return {"status": "ok", "builder_loaded": builder is not None}

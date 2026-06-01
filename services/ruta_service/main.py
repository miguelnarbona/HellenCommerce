import asyncio
import os
import sys
import json
import datetime
import websockets
import platform
import httpx
from typing import Optional
import platform

system = platform.system()
sys.path.append("c:/HellenCommerce") if system == "Windows" else sys.path.append("/app")

from app.utils.paths import hc_path, data_path
from app.core.pipeline.map_logic import MapLogic
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import httpx

from app.builder.AppBuilder import AppBuilder

# CONFIGURACION
system = platform.system() 

# Shared libraries
sys.path.append("c:/HellenCommerce")
LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://logging_service:8099/ws/logs")
ruta_model = None
builder = None
MODEL_UP_URL = os.getenv("MODEL_UP_URL", "http://model_up_service:8040/infer")
MODEL_PATH = data_path("mistral/mistral-7b-instruct-v0.2.Q4_K_M/mistral-7b-instruct-v0.2.Q4_K_M.gguf")

class ProcessRequest(BaseModel):
    user_id: str
    prompt: str
    # Optional coordinates for route calculation
    lat_origen: Optional[float] = None
    lon_origen: Optional[float] = None
    lat_destino: Optional[float] = None
    lon_destino: Optional[float] = None

# ============================================================
# LOGGING AL LOGGING_SERVICE
# ============================================================
async def log_to_logging_service(level: str, msg: str, status_flag="SOLUCIONADO", line_num=0):
    try:
        async with websockets.connect(LOGGING_WS_URL) as ws:
            payload = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "log_level": level,
                "service_origin": "ruta_service",
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
        print(f"[DEBUG] Error enviando log (ruta): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ruta_model, builder
    await log_to_logging_service("INFO", "Iniciando Ruta Service", line_num=45)
    
    try:
        builder = AppBuilder()
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al inicializar AppBuilder: {e}", line_num=49)

    system = platform.system()

    await log_to_logging_service("INFO", f"RUTA Service iniciado. Delegará inferencia a {MODEL_UP_URL}", line_num=0)


    yield
    ruta_model = None

app = FastAPI(title="Specialized Service - RUTA", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    user_id = req.user_id
    prompt = req.prompt
    # Extract optional coordinates
    lat_origen = req.lat_origen
    lon_origen = req.lon_origen
    lat_destino = req.lat_destino
    lon_destino = req.lon_destino
    
    try:
        # Obtenemos la última interacción del usuario (el último vendedor/comprador consultado)
        db_context = await asyncio.to_thread(
            builder.business_logic._entregar_datos_previos,
            user_id
        )
        
        content = db_context.get("content", [])
        
        # En la vida real aquí llamaríamos a builder.map_logic.calcular_ruta(user_id, destino_lat, destino_lon)
        # Asumiremos que el content (last_vendor) tiene la ubicación del destino.
        
        prompt_mistral = f'''[INST] Eres un asistente especialista en RUTA.
        El usuario ha enviado: {prompt}
        Responde de manera clara, profesional y concisa.
        [/INST]'''

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                model_path = MODEL_PATH
                payload = {"model": model_path, "prompt": prompt_mistral, "max_tokens": 200, "temperature": 0.3}
                resp = await client.post(MODEL_UP_URL, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data.get("result"), dict):
                        partial_response = data["result"].get("choices", [{}])[0].get("text", "").strip()
                    else:
                        partial_response = str(data.get("result"))
                else:
                    partial_response = "Estoy calculando la mejor ruta para ti."
        except Exception as e:
            await log_to_logging_service("ERROR", f"Error calling model-up-service: {e}", line_num=0)
            partial_response = "Estoy calculando la mejor ruta para ti."
            
        await log_to_logging_service("INFO", f"Proceso RUTA completado para {user_id}", line_num=108)
        response = {"intent": "RUTA", "partial": partial_response}
        # If coordinates provided, fetch route from MapLogic
        if all(v is not None for v in [lat_origen, lon_origen, lat_destino, lon_destino]):
            try:
                map_logic = MapLogic()
                route_info = map_logic.obtener_ruta(
                    lat_origen, lon_origen, lat_destino, lon_destino
                )
                if route_info:
                    response["route"] = route_info
            except Exception as e:
                await log_to_logging_service("WARNING", f"Error fetching route: {e}", line_num=0)
        return response
        
    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando RUTA para {user_id}: {e}", line_num=112)
        return {"intent": "RUTA", "partial": "Hubo un problema procesando la ruta."}

@app.get("/health")
def health():
    return {"status": "ok"}

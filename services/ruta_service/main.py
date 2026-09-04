"""
HellenCommerce 2.0.1 - ruta_service
Procesa intenciones de RUTA. Inferencia delegada a HuggingFace Serverless API.
"""
import asyncio
import os
import sys
import json
import datetime
import websockets
import platform
from typing import Optional

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from pydantic import BaseModel
from contextlib import asynccontextmanager

system = platform.system()
sys.path.append("c:/HellenCommerce") if system == "Windows" else sys.path.append("/app")
from app.builder.AppBuilder import AppBuilder
from app.shared.hf_infer import call_mistral
from app.core.pipeline.map_logic import MapLogic

LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://bunker_logging_service:8099/ws/logs")
builder = None

class ProcessRequest(BaseModel):
    user_id: str
    prompt: str
    lat_origen: Optional[float] = None
    lon_origen: Optional[float] = None
    lat_destino: Optional[float] = None
    lon_destino: Optional[float] = None

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
    global builder
    await log_to_logging_service("INFO", "Iniciando Ruta Service", line_num=0)
    try:
        builder = AppBuilder()
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al inicializar AppBuilder: {e}", line_num=0)
        
    await log_to_logging_service("INFO", "RUTA Service iniciado. Inferencia → HuggingFace Serverless API", line_num=0)
    yield
    print("Ruta Service apagándose")

app = FastAPI(title="Specialized Service - RUTA", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    user_id = req.user_id
    prompt = req.prompt
    
    lat_origen = req.lat_origen
    lon_origen = req.lon_origen
    lat_destino = req.lat_destino
    lon_destino = req.lon_destino
    
    try:
        db_context = await asyncio.to_thread(
            builder.business_logic._entregar_datos_previos,
            user_id
        )
        content = db_context.get("content", [])
        
        prompt_mistral = f'''[INST] Eres un asistente especialista en RUTA.
        El usuario ha enviado: {prompt}
        Responde de manera clara, profesional y concisa sobre la ruta.
        [/INST]'''
        
        partial_response = await call_mistral(
            prompt_mistral,
            fallback="Estoy calculando la mejor ruta para ti."
        )
            
        await log_to_logging_service("INFO", f"Proceso RUTA completado para {user_id}", line_num=0)
        
        response = {"intent": "RUTA", "partial": partial_response}
        
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
        await log_to_logging_service("ERROR", f"Error procesando RUTA para {user_id}: {e}", line_num=0)
        return {"intent": "RUTA", "partial": "Hubo un problema procesando la ruta."}

@app.get("/health")
def health():
    return {"status": "ok"}

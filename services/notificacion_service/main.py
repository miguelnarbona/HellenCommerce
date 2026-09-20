"""
HellenCommerce 2.0.1 - notificacion_service
Procesa intenciones de NOTIFICACION. Inferencia delegada a HuggingFace Serverless API.
"""
import asyncio
import os
import sys
import json
import datetime
import websockets
import platform

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from pydantic import BaseModel
from contextlib import asynccontextmanager

system = platform.system()
sys.path.append("c:/HellenCommerce") if system == "Windows" else sys.path.append("/app")
from app.builder.AppBuilder import AppBuilder
from app.shared.hf_infer import call_mistral

LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://bunker_logging_service:8099/ws/logs")
builder = None

class ProcessRequest(BaseModel):
    user_id: str
    prompt: str

async def log_to_logging_service(level: str, msg: str, status_flag="SOLUCIONADO", line_num=0):
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        async with websockets.connect(LOGGING_WS_URL) as ws:
            payload = {
                "timestamp": now.isoformat(),
                "log_level": level,
                "service_origin": "notificacion_service",
                "source_file": "main.py",
                "line_number": line_num,
                "file_path": __file__,
                "code_snippet": str(msg),
                "error_description": str(msg) if level in ["ERROR", "WARNING"] else "",
                "proposed_solution": "",
                "status_flag": status_flag
            }
            print(f"[DEBUG] Enviando log (notificacion): {payload}")
            await ws.send(json.dumps(payload))
            await asyncio.sleep(0.01) 
    except Exception as e:
        print(f"[DEBUG] Error enviando log (notificacion): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global builder
    await log_to_logging_service("INFO", "Iniciando Notificacion Service", line_num=0)
    try:
        builder = AppBuilder()
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al inicializar AppBuilder: {e}", line_num=0)
        
    await log_to_logging_service("INFO", "NOTIFICACION Service iniciado. Inferencia → HuggingFace Serverless API", line_num=0)
    yield
    print("Notificacion Service apagándose")

app = FastAPI(title="Specialized Service - NOTIFICACION", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    """
    Procesa intenciones de tipo NOTIFICACION.
    Recibe el prompt ya ensamblado por el orquestador y lo ejecuta en Mistral/HF.
    """
    user_id = req.user_id
    prompt  = req.prompt

    try:
        partial_response = await call_mistral(
            prompt,
            fallback="No se pudo generar una respuesta en este momento."
        )

        await log_to_logging_service("INFO", f"Proceso NOTIFICACION completado para {user_id}", line_num=0)
        return {"intent": "NOTIFICACION", "partial": partial_response}

    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando NOTIFICACION para {user_id}: {e}", line_num=0)
        return {"intent": "NOTIFICACION", "partial": "Hubo un problema procesando tu solicitud."}

@app.get("/health")
def health():
    return {"status": "ok"}

"""
HellenCommerce 2.0.1 - compra_service
Procesa intenciones de COMPRA. Inferencia delegada a HuggingFace Serverless API.
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

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

system = platform.system()
sys.path.append("c:/HellenCommerce") if system == "Windows" else sys.path.append("/app")
from app.builder.AppBuilder import AppBuilder
from app.shared.hf_infer import call_mistral

LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://bunker_logging_service:8099/ws/logs")
compra_model = None
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
                "service_origin": "compra_service",
                "source_file": "main.py",
                "line_number": line_num,
                "file_path": __file__,
                "code_snippet": str(msg),
                "error_description": str(msg) if level in ["ERROR", "WARNING"] else "",
                "proposed_solution": "",
                "status_flag": status_flag
            }
            print(f"[DEBUG] Enviando log (compra): {payload}")
            await ws.send(json.dumps(payload))
            await asyncio.sleep(0.01) 
    except Exception as e:
        print(f"[DEBUG] Error enviando log (compra): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global compra_model, builder
    await log_to_logging_service("INFO", "Iniciando Compra Service", line_num=46)
    try:
        builder = AppBuilder()
        builder.load_embeddings()
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al inicializar AppBuilder: {e}", line_num=52)
    await log_to_logging_service("INFO", "COMPRA Service iniciado. Inferencia → HuggingFace Serverless API", line_num=0)
    yield
    compra_model = None
    print("Compra Service apagándose")

app = FastAPI(title="Specialized Service - COMPRA", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    """
    Procesa intenciones de tipo COMPRA.
    Recibe el prompt ya ensamblado por el orquestador y lo ejecuta en Mistral/HF.
    """
    user_id = req.user_id
    prompt  = req.prompt

    try:
        partial_response = await call_mistral(
            prompt,
            fallback="No se pudo generar una respuesta en este momento."
        )

        await log_to_logging_service("INFO", f"Proceso COMPRA completado para {user_id}", line_num=0)
        return {"intent": "COMPRA", "partial": partial_response}

    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando COMPRA para {user_id}: {e}", line_num=0)
        return {"intent": "COMPRA", "partial": "Hubo un problema procesando tu solicitud."}

@app.get("/health")
def health():
    return {"status": "ok"}

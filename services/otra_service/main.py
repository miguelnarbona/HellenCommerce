"""
HellenCommerce 2.0.1 - otra_service
Procesa intenciones OTRA. Inferencia delegada a HuggingFace Serverless API.
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
from app.shared.hf_infer import call_mistral

LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://bunker_logging_service:8099/ws/logs")

class ProcessRequest(BaseModel):
    user_id: str
    prompt: str

async def log_to_logging_service(level: str, msg: str, status_flag="SOLUCIONADO", line_num=0):
    try:
        async with websockets.connect(LOGGING_WS_URL) as ws:
            payload = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "log_level": level,
                "service_origin": "otra_service",
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
        print(f"[DEBUG] Error enviando log (otra): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await log_to_logging_service("INFO", "Iniciando Otra Service", line_num=0)
    await log_to_logging_service("INFO", "OTRA Service iniciado. Inferencia → HuggingFace Serverless API", line_num=0)
    yield
    print("Otra Service apagándose")

app = FastAPI(title="Specialized Service - OTRA", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    user_id = req.user_id
    prompt = req.prompt
    
    try:
        prompt_mistral = f'''[INST] Eres un asistente especialista en OTRA.
        El usuario ha enviado un mensaje genérico o no clasificado: {prompt}
        Responde de manera clara, profesional y concisa.
        [/INST]'''
        
        partial_response = await call_mistral(
            prompt_mistral,
            fallback="Estoy procesando tu mensaje. Por favor espera un momento."
        )
            
        await log_to_logging_service("INFO", f"Proceso OTRA completado para {user_id}", line_num=0)
        return {"intent": "OTRA", "partial": partial_response}
        
    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando OTRA para {user_id}: {e}", line_num=0)
        return {"intent": "OTRA", "partial": "Lo siento, tuve un problema interno."}

@app.get("/health")
def health():
    return {"status": "ok"}

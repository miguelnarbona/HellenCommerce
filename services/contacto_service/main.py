"""
HellenCommerce 2.0.1 - contacto_service
Procesa intenciones de CONTACTO. Inferencia delegada a HuggingFace Serverless API.
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

LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://127.0.0.1:8099/ws/logs")
builder = None

class ProcessRequest(BaseModel):
    user_id: str
    prompt: str

async def log_to_logging_service(level: str, msg: str, status_flag="SOLUCIONADO", line_num=0):
    try:
        async with websockets.connect(LOGGING_WS_URL) as ws:
            payload = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "log_level": level,
                "service_origin": "contacto_service",
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
        print(f"[DEBUG] Error enviando log (contacto): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global builder
    await log_to_logging_service("INFO", "Iniciando Contacto Service", line_num=0)
    try:
        builder = AppBuilder()
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al inicializar AppBuilder: {e}", line_num=0)
        
    await log_to_logging_service("INFO", "CONTACTO Service iniciado. Inferencia → HuggingFace Serverless API", line_num=0)
    yield
    print("Contacto Service apagándose")

app = FastAPI(title="Specialized Service - CONTACTO", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    user_id = req.user_id
    prompt = req.prompt
    
    try:
        # El contacto asume devolver el vendedor previo interactuado
        db_context = await asyncio.to_thread(
            builder.business_logic._entregar_datos_previos,
            user_id
        )
        
        content = db_context.get("content", [])
        content_json = json.dumps(content, ensure_ascii=False) if content else "Sin información previa de contacto."
        
        prompt_mistral = f'''[INST] Eres un asistente especialista en CONTACTO.
        El usuario ha enviado: {prompt}
        Datos previos de contacto: {content_json}
        Responde de manera clara, profesional y concisa con los datos de contacto.
        [/INST]'''
        
        partial_response = await call_mistral(
            prompt_mistral,
            fallback="Estoy recuperando información de contacto."
        )
            
        await log_to_logging_service("INFO", f"Proceso CONTACTO completado para {user_id}", line_num=0)
        return {"intent": "CONTACTO", "partial": partial_response}
        
    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando CONTACTO para {user_id}: {e}", line_num=0)
        return {"intent": "CONTACTO", "partial": "Hubo un problema procesando la información de contacto."}

@app.get("/health")
def health():
    return {"status": "ok"}

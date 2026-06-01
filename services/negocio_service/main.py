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
import httpx

system = platform.system()
sys.path.append("c:/HellenCommerce") if system == "Windows" else sys.path.append("/app")
from app.utils.paths import data_path
from app.builder.AppBuilder import AppBuilder

LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://logging_service:8099/ws/logs")
negocio_model = None
builder = None
MODEL_UP_URL = os.getenv("MODEL_UP_URL", "http://model_up_service:8040/infer")

class ProcessRequest(BaseModel):
    user_id: str
    prompt: str

async def log_to_logging_service(level: str, msg: str, status_flag="SOLUCIONADO", line_num=0):
    try:
        async with websockets.connect(LOGGING_WS_URL) as ws:
            payload = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "log_level": level,
                "service_origin": "negocio_service",
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
        print(f"[DEBUG] Error enviando log (negocio): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global negocio_model, builder
    await log_to_logging_service("INFO", "Iniciando Negocio Microservice", line_num=43)
    
    try:
        builder = AppBuilder()
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al inicializar AppBuilder: {e}", line_num=47)

    system = platform.system()

    await log_to_logging_service("INFO", f"NEGOCIO Service iniciado. Delegará inferencia a {MODEL_UP_URL}", line_num=0)


    yield
    negocio_model = None

app = FastAPI(title="Specialized Service - NEGOCIO", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    user_id = req.user_id
    prompt = req.prompt
    
    try:
        db_context = await asyncio.to_thread(
            builder.business_logic.process,
            prompt,
            "negocio",
            user_id,
            None
        )
        
        content = db_context.get("content", [])
        if isinstance(content, list) and len(content) > 3:
            content = content[:3]
            
        try:
            
            async with httpx.AsyncClient(timeout=60.0) as client:
            
                model_path = os.getenv("NEGOCIO_MODEL_PATH", data_path("mistral/mistral-7b-instruct-v0.2.Q4_K_M/mistral-7b-instruct-v0.2.Q4_K_M.gguf"))
            
                payload = {"model": model_path, "prompt": prompt_mistral, "max_tokens": 200, "temperature": 0.3}
            
                resp = await client.post(MODEL_UP_URL, json=payload)
            
                if resp.status_code == 200:
            
                    data = resp.json()
            
                    if isinstance(data.get("result"), dict):
            
                        partial_response = data["result"].get("choices", [{}])[0].get("text", "").strip()
            
                    else:
            
                        partial_response = str(data.get("result"))
            
                else:
            
                    partial_response = "Estoy buscando negocios cercanos para ti."
            
        except Exception as e:
            
            await log_to_logging_service("ERROR", f"Error calling model-up-service: {e}", line_num=0)
            
            partial_response = "Estoy buscando negocios cercanos para ti."
            
        await log_to_logging_service("INFO", f"Proceso NEGOCIO completado para {user_id}", line_num=105)
        return {"intent": "NEGOCIO", "partial": partial_response}
        
    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando NEGOCIO para {user_id}: {e}", line_num=109)
        return {"intent": "NEGOCIO", "partial": "Hubo un problema procesando tu solicitud de negocio."}

@app.get("/health")
def health():
    return {"status": "ok"}

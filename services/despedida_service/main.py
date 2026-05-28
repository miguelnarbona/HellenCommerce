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
import httpx

LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://logging_service:8099/ws/logs")
MODEL_UP_URL = os.getenv("MODEL_UP_URL", "http://model_up_service:8030/infer")
despedida_model = None

class ProcessRequest(BaseModel):
    user_id: str
    prompt: str

async def log_to_logging_service(level: str, msg: str, status_flag="SOLUCIONADO", line_num=0):
    try:
        async with websockets.connect(LOGGING_WS_URL) as ws:
            payload = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "log_level": level,
                "service_origin": "despedida_service",
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
        print(f"[DEBUG] Error enviando log (despedida): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global despedida_model
    await log_to_logging_service("INFO", "Iniciando Despedida Microservice", line_num=41)

    system = platform.system()

    await log_to_logging_service("INFO", f"DESPEDIDA Service iniciado. Delegará inferencia a {MODEL_UP_URL}", line_num=0)


    yield
    despedida_model = None

app = FastAPI(title="Specialized Service - DESPEDIDA", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    user_id = req.user_id
    prompt = req.prompt
    
    try:
        prompt_mistral = f'''[INST] Eres un asistente especialista en DESPEDIDA.
El usuario ha enviado: {prompt}
Responde de manera clara, profesional y concisa.
[/INST]'''
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                model_path = os.getenv("DESPEDIDA_MODEL_PATH", "c:/HellenData/mistral/mistral-7b-instruct-v0.2.Q4_K_M/mistral-7b-instruct-v0.2.Q4_K_M.gguf")
                payload = {"model": model_path, "prompt": prompt_mistral, "max_tokens": 200, "temperature": 0.3}
                resp = await client.post(MODEL_UP_URL, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data.get("result"), dict):
                        partial_response = data["result"].get("choices", [{}])[0].get("text", "").strip()
                    else:
                        partial_response = str(data.get("result"))
                else:
                    partial_response = "¡Hasta luego! Estoy aquí cuando me necesites."
        except Exception as e:
            await log_to_logging_service("ERROR", f"Error calling model-up-service: {e}", line_num=0)
            partial_response = "¡Hasta luego! Estoy aquí cuando me necesites."
            
        await log_to_logging_service("INFO", f"Proceso DESPEDIDA completado para {user_id}", line_num=84)
        return {"intent": "DESPEDIDA", "partial": partial_response}
        
    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando DESPEDIDA para {user_id}: {e}", line_num=88)
        return {"intent": "DESPEDIDA", "partial": "¡Adiós!"}

@app.get("/health")
def health():
    return {"status": "ok"}

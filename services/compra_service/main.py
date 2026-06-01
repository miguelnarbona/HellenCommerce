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

# Shared libraries
system = platform.system()
sys.path.append("c:/HellenCommerce") if system == "Windows" else sys.path.append("/app")
from app.utils.paths import data_path
from app.builder.AppBuilder import AppBuilder

LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://127.0.0.1:8099/ws/logs")
compra_model = None
builder = None
MODEL_UP_URL = os.getenv("MODEL_UP_URL", "http://model_up_service:8030/infer")

class ProcessRequest(BaseModel):
    user_id: str
    prompt: str

# ============================================================
# LOGGING AL LOGGING_SERVICE
# ============================================================
async def log_to_logging_service(level: str, msg: str, status_flag="SOLUCIONADO", line_num=0):
    try:
        async with websockets.connect(LOGGING_WS_URL) as ws:
            payload = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "log_level": level,
                "service_origin": "compra_service",
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
        print(f"[DEBUG] Error enviando log (compra): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global compra_model, builder
    await log_to_logging_service("INFO", "Iniciando Compra Service y cargando dependencias BD", line_num=46)
    
    try:
        builder = AppBuilder()
        builder.load_embeddings()
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al inicializar AppBuilder: {e}", line_num=52)

    system = platform.system()

    await log_to_logging_service("INFO", f"COMPRA Service iniciado. Delegará inferencia a {MODEL_UP_URL}", line_num=0)


    yield
    compra_model = None
    print("Compra Service apagándose")

app = FastAPI(title="Specialized Service - COMPRA", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    """
    Procesa intenciones de tipo COMPRA.
    Extrae la mercancía del prompt (o asume el mensaje), busca vendedores, y genera un parcial.
    """
    user_id = req.user_id
    prompt = req.prompt
    
    try:
        # En el caso de COMPRA, el usuario asume el rol de "comprador"
        # y buscamos "vendedores"
        db_context = await asyncio.to_thread(
            builder.business_logic.process,
            prompt,         
            "comprador",
            user_id,
            None
        )
        
        content = db_context.get("content", [])
        if isinstance(content, list) and len(content) > 3:
            content = content[:3]
            
        try:
            
            async with httpx.AsyncClient(timeout=60.0) as client:
            
                model_path = os.getenv("COMPRA_MODEL_PATH", data_path("mistral/mistral-7b-instruct-v0.2.Q4_K_M/mistral-7b-instruct-v0.2.Q4_K_M.gguf"))
            
                payload = {"model": model_path, "prompt": prompt_mistral, "max_tokens": 200, "temperature": 0.3}
            
                resp = await client.post(MODEL_UP_URL, json=payload)
            
                if resp.status_code == 200:
            
                    data = resp.json()
            
                    if isinstance(data.get("result"), dict):
            
                        partial_response = data["result"].get("choices", [{}])[0].get("text", "").strip()
            
                    else:
            
                        partial_response = str(data.get("result"))
            
                else:
            
                    partial_response = "Ventas encontradas: no pude generar la respuesta completa ahora."
            
        except Exception as e:
            
            await log_to_logging_service("ERROR", f"Error calling model-up-service: {e}", line_num=0)
            
            partial_response = "Ventas encontradas: no pude generar la respuesta completa ahora."
            
        await log_to_logging_service("INFO", f"Proceso COMPRA completado para {user_id}", line_num=116)
        return {"intent": "COMPRA", "partial": partial_response}
        
    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando COMPRA para {user_id}: {e}", line_num=120)
        return {"intent": "COMPRA", "partial": "Hubo un problema procesando tu compra."}

@app.get("/health")
def health():
    return {"status": "ok"}

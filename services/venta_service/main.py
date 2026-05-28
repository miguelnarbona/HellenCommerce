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

# Shared libraries (simulated sys.path for this migration)
sys.path.append("c:/HellenCommerce")
from app.builder.AppBuilder import AppBuilder

LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://127.0.0.1:8099/ws/logs")
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
                "service_origin": "venta_service",
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
        print(f"[DEBUG] Error enviando log (venta): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global venta_model, builder
    await log_to_logging_service("INFO", "Iniciando Venta Service y cargando dependencias BD", line_num=47)
    
    try:
        builder = AppBuilder()
        builder.load_embeddings()
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al inicializar AppBuilder: {e}", line_num=53)

    # The service delegates model inference to the centralized model-up-service.
    await log_to_logging_service("INFO", f"Venta Service iniciado. Delegará inferencia a {MODEL_UP_URL}", line_num=71)

    yield
    venta_model = None
    print("Venta Service apagándose")

app = FastAPI(title="Specialized Service - VENTA", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    """
    Procesa intenciones de tipo VENTA.
    Extrae la mercancía del prompt (o asume el mensaje), busca compradores, y genera un parcial.
    """
    user_id = req.user_id
    prompt = req.prompt
    
    try:
        # En el caso de VENTA, el usuario asume el rol de "vendedor"
        # y buscamos "compradores"
        db_context = await asyncio.to_thread(
            builder.business_logic.process,
            prompt,         # usamos el prompt como mensaje para extraer nucleo
            "vendedor",
            user_id,
            None
        )
        
        # Filtramos resultados
        content = db_context.get("content", [])
        if isinstance(content, list) and len(content) > 3:
            # Filtro simplificado
            content = content[:3]
            
        # Utilizamos el LLM especializado en VENTA para formular una respuesta amigable
        # Build a specialized prompt for VENTA
        db_json = json.dumps(content, ensure_ascii=False) if content else "Ningún comprador encontrado."
        prompt_mistral = f"""[INST] Eres el asistente especialista en VENTA. 
El usuario ha manifestado intención de vender.
Mensaje del usuario: {prompt}
Datos encontrados en la base de datos (compradores interesados): {db_json}

Redacta un breve reporte indicando si se encontraron compradores. Sé conciso y profesional.
[/INST]"""

        # Delegate inference to model-up-service
        prompt_mistral = f'''[INST] Eres un asistente especialista en VENTA.
El usuario ha enviado: {prompt}
Responde de manera clara, profesional y concisa.
[/INST]'''
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                model_path = os.getenv("VENTA_MODEL_PATH", "c:/HellenData/mistral/mistral-7b-instruct-v0.2.Q4_K_M/mistral-7b-instruct-v0.2.Q4_K_M.gguf")
                payload = {"model": model_path, "prompt": prompt_mistral, "max_tokens": 200, "temperature": 0.3}
                resp = await client.post(MODEL_UP_URL, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    # Normalize result shape from llama_cpp or model-up
                    if isinstance(data.get("result"), dict):
                        # llama_cpp result
                        partial_response = data["result"].get("choices", [{}])[0].get("text", "").strip()
                    else:
                        partial_response = str(data.get("result"))
                else:
                    partial_response = f"Ventas encontradas: {len(content)} prospectos. (inference error)"
        except Exception as e:
            await log_to_logging_service("ERROR", f"Error calling model-up-service: {e}", line_num=116)
            partial_response = f"Ventas encontradas: {len(content)} prospectos. (inference error)"
            
        await log_to_logging_service("INFO", f"Proceso VENTA completado para {user_id}", line_num=118)
        return {"intent": "VENTA", "partial": partial_response}
        
    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando VENTA para {user_id}: {e}", line_num=122)
        return {"intent": "VENTA", "partial": "Hubo un problema procesando tu venta."}

@app.get("/health")
def health():
    return {"status": "ok"}

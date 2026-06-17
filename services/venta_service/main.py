"""
HellenCommerce 2.0.1 - venta_service
Procesa intenciones de VENTA. Inferencia delegada a HuggingFace Serverless API.
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
    global builder
    await log_to_logging_service("INFO", "Iniciando Venta Service", line_num=47)
    try:
        builder = AppBuilder()
        builder.load_embeddings()
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al inicializar AppBuilder: {e}", line_num=53)
    await log_to_logging_service("INFO", "VENTA Service iniciado. Inferencia → HuggingFace Serverless API", line_num=0)
    yield
    print("Venta Service apagándose")

app = FastAPI(title="Specialized Service - VENTA", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    """
    Procesa intenciones de tipo VENTA.
    Busca compradores y genera respuesta via HF Serverless API.
    """
    user_id = req.user_id
    prompt  = req.prompt

    try:
        db_context = await asyncio.to_thread(
            builder.business_logic.process,
            prompt, "vendedor", user_id, None
        )
        content = db_context.get("content", [])
        if isinstance(content, list) and len(content) > 3:
            content = content[:3]

        db_json = json.dumps(content, ensure_ascii=False) if content else "Ningún comprador encontrado."
        prompt_mistral = f"""[INST] Eres el asistente especialista en VENTA.
        El usuario ha manifestado intención de vender.
        Mensaje del usuario: {prompt}
        Compradores interesados encontrados: {db_json}

        Redacta un breve reporte indicando si se encontraron compradores. Sé conciso y profesional.
        [/INST]"""

        partial_response = await call_mistral(
            prompt_mistral,
            fallback=f"Ventas encontradas: {len(content)} prospectos."
        )

        await log_to_logging_service("INFO", f"Proceso VENTA completado para {user_id}", line_num=0)
        return {"intent": "VENTA", "partial": partial_response}

    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando VENTA para {user_id}: {e}", line_num=0)
        return {"intent": "VENTA", "partial": "Hubo un problema procesando tu venta."}

@app.get("/health")
def health():
    return {"status": "ok"}

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
    Extrae la mercancía del prompt, busca vendedores, y genera respuesta via HF.
    """
    user_id = req.user_id
    prompt  = req.prompt

    try:
        db_context = await asyncio.to_thread(
            builder.business_logic.process,
            prompt, "comprador", user_id, None
        )
        content = db_context.get("content", [])
        if isinstance(content, list) and len(content) > 3:
            content = content[:3]

        db_json = json.dumps(content, ensure_ascii=False) if content else "Ningún vendedor encontrado."
        prompt_mistral = f"""[INST] Eres el asistente especialista en COMPRA.
        El usuario ha manifestado intención de comprar.
        Mensaje del usuario: {prompt}
        Vendedores encontrados: {db_json}

        Redacta un breve reporte indicando si se encontraron vendedores. Sé conciso y profesional.
        [/INST]"""

        partial_response = await call_mistral(
            prompt_mistral,
            fallback="Compras encontradas: no pude generar la respuesta completa ahora."
        )

        await log_to_logging_service("INFO", f"Proceso COMPRA completado para {user_id}", line_num=0)
        return {"intent": "COMPRA", "partial": partial_response}

    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando COMPRA para {user_id}: {e}", line_num=0)
        return {"intent": "COMPRA", "partial": "Hubo un problema procesando tu compra."}

@app.get("/health")
def health():
    return {"status": "ok"}

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

LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://logging_service:8099/ws/logs")
informativa_model = None
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
                "service_origin": "informativa_service",
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
        print(f"[DEBUG] Error enviando log (informativa): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global informativa_model, builder
    await log_to_logging_service("INFO", "Iniciando Informativa Service", line_num=45)
    
    try:
        builder = AppBuilder()
        builder.load_embeddings()
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al inicializar AppBuilder (RAG/Embedder): {e}", line_num=51)

    system = platform.system()

    await log_to_logging_service("INFO", f"INFORMATIVA Service iniciado. Delegará inferencia a {MODEL_UP_URL}", line_num=0)


    yield
    informativa_model = None

app = FastAPI(title="Specialized Service - INFORMATIVA", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    """
    Resuelve intenciones INFORMATIVA.
    Utiliza el RAG (ChromaDB + Embeddings) para buscar respuestas semánticas en la base de conocimientos.
    """
    user_id = req.user_id
    prompt = req.prompt
    
    try:
        rag_context = ""
        if builder and builder.get_rag and builder.embedder:
            # Embeber la pregunta y consultar ChromaDB
            rag = builder.get_rag()
            emb = await asyncio.to_thread(builder.embedder.embed, prompt)
            rag_results = await asyncio.to_thread(rag.query, emb, 3)

            if rag_results:
                rag_context = "\n".join([r["text"] for r in rag_results])
                
        prompt_mistral = f'''[INST] Eres un asistente especialista en INFORMATIVA.
El usuario ha enviado: {prompt}
Responde de manera clara, profesional y concisa.
[/INST]'''
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                model_path = os.getenv("INFORMATIVA_MODEL_PATH", data_path("mistral/mistral-7b-instruct-v0.2.Q4_K_M/mistral-7b-instruct-v0.2.Q4_K_M.gguf"))
                payload = {"model": model_path, "prompt": prompt_mistral, "max_tokens": 200, "temperature": 0.3}
                resp = await client.post(MODEL_UP_URL, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data.get("result"), dict):
                        partial_response = data["result"].get("choices", [{}])[0].get("text", "").strip()
                    else:
                        partial_response = str(data.get("result"))
                else:
                    partial_response = "Estoy consultando la información disponible para darte respuesta."
        except Exception as e:
            await log_to_logging_service("ERROR", f"Error calling model-up-service: {e}", line_num=0)
            partial_response = "Estoy consultando la información disponible para darte respuesta."
            
        await log_to_logging_service("INFO", f"Proceso INFORMATIVA completado para {user_id}", line_num=110)
        return {"intent": "INFORMATIVA", "partial": partial_response}
        
    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando INFORMATIVA para {user_id}: {e}", line_num=114)
        return {"intent": "INFORMATIVA", "partial": "Hubo un problema recuperando la información."}

@app.get("/health")
def health():
    return {"status": "ok"}

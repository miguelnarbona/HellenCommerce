"""
HellenCommerce 2.0.1 - informativa_service
Procesa intenciones INFORMATIVA. Inferencia delegada a HuggingFace Serverless API.
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
    global builder
    await log_to_logging_service("INFO", "Iniciando Informativa Service", line_num=0)
    try:
        builder = AppBuilder()
        builder.load_embeddings()
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al inicializar AppBuilder (RAG/Embedder): {e}", line_num=0)
        
    await log_to_logging_service("INFO", "INFORMATIVA Service iniciado. Inferencia → HuggingFace Serverless API", line_num=0)
    yield
    print("Informativa Service apagándose")

app = FastAPI(title="Specialized Service - INFORMATIVA", lifespan=lifespan)

@app.post("/process")
async def process_intent(req: ProcessRequest):
    """
    Resuelve intenciones INFORMATIVA.
    Utiliza el RAG (ChromaDB + Embeddings) para buscar respuestas semánticas.
    """
    user_id = req.user_id
    prompt = req.prompt
    
    try:
        rag_context = ""
        if builder and builder.get_rag and builder.embedder:
            rag = builder.get_rag()
            emb = await asyncio.to_thread(builder.embedder.embed, prompt)
            rag_results = await asyncio.to_thread(rag.query, emb, 3)

            if rag_results:
                rag_context = "\n".join([r["text"] for r in rag_results])
                
        prompt_mistral = f'''[INST] Eres un asistente especialista en INFORMATIVA.
        El usuario ha enviado: {prompt}
        Contexto recuperado de la base de conocimientos: {rag_context}
        Responde de manera clara, profesional y concisa usando el contexto si es útil.
        [/INST]'''
        
        partial_response = await call_mistral(
            prompt_mistral,
            fallback="Estoy consultando la información disponible para darte respuesta."
        )
            
        await log_to_logging_service("INFO", f"Proceso INFORMATIVA completado para {user_id}", line_num=0)
        return {"intent": "INFORMATIVA", "partial": partial_response}
        
    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando INFORMATIVA para {user_id}: {e}", line_num=0)
        return {"intent": "INFORMATIVA", "partial": "Hubo un problema recuperando la información."}

@app.get("/health")
def health():
    return {"status": "ok"}

import asyncio
import os
import sys
import platform
import httpx
import websockets
import json
import datetime

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from pydantic import BaseModel
from contextlib import asynccontextmanager
from llama_cpp import Llama

class SynthesisRequest(BaseModel):
    partials: list[dict]
    
# CONFIGURACIONES
mistral_model = None
system = platform.system()    
LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://logging_service:8099/ws/logs")
MODEL_PATH = f"c:/HellenData/Qwen/Qwen2.5-3B-Instruct-GGUF/qwen2.5-3b-instruct-q4_k_m.gguf" if system == "Windows" else "/app/models/qwen/Qwen2.5-3B-Instruct-GGUF/qwen2.5-3b-instruct-q4_k_m.gguf"

# ============================================================
# LOGGING AL LOGGING_SERVICE
# ============================================================
async def log_to_logging_service(level: str, msg: str, status_flag="SOLUCIONADO", line_num=0):
    try:
        async with websockets.connect(LOGGING_WS_URL) as ws:
            payload = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "log_level": level,
                "service_origin": "mistral_service",
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
        print(f"[DEBUG] Error enviando log (mistral): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global mistral_model
    system = platform.system()
    
    await log_to_logging_service("INFO", "Iniciando Mistral Service para consolidar multi-intenciones", line_num=47)

    print(f"Cargando modelo de propósito general Mistral desde: {MODEL_PATH}")
    try:
        mistral_model = Llama(
            model_path=MODEL_PATH,
            n_ctx=4096,
            n_threads=4,
            n_batch=256,
            use_mmap=True,
            use_mlock=False
        )
        await log_to_logging_service("INFO", f"Modelo Mistral GGUF cargado exitosamente", line_num=64)
    except Exception as e:
        await log_to_logging_service("ERROR", f"Fallo al cargar Mistral: {e}", line_num=66)

    yield
    mistral_model = None
    print("Mistral Service apagándose")

app = FastAPI(title="Mistral Unification Service", lifespan=lifespan)

@app.post("/synthesize")
async def synthesize_responses(req: SynthesisRequest):
    partials = req.partials
    
    # Si solo hay una respuesta parcial y no queremos modificarla, podemos devolverla directamente.
    # Pero la directiva indica: "Mistral sintetiza y unifica todo en una sola respuesta cohesiva, libre de errores, alucinaciones o repeticiones"
    
    texto_parciales = ""
    for idx, partial in enumerate(partials):
        intent = partial.get("intent", "OTRA")
        content = partial.get("partial", "")
        texto_parciales += f"\n[Información de {intent}]: {content}"
        
    prompt_mistral = f"""
    [INST] Eres el asistente principal. Tu tarea es unificar y redactar una única respuesta final y cohesiva para el usuario basándote en la siguiente información fragmentada que proviene de distintos servicios especializados.
    Redacta de manera natural, amable y directa. NO repitas información. NO menciones que la información viene de "diferentes servicios" ni Uses "[Información de...]".
    
    Información fragmentada a unificar:
    {texto_parciales}
    [/INST]
    """
    
    if mistral_model:
        try:
            result = mistral_model(
                prompt=prompt_mistral,
                max_tokens=512,
                temperature=0.3,
                top_p=0.9
            )
            final_response = result["choices"][0]["text"].strip()
            return {"response": final_response}
        except Exception as e:
            await log_to_logging_service("ERROR", f"Error en inferencia de unificación Mistral: {e}", line_num=107)
            return {"response": "Lo siento, tuve un problema técnico al unificar las respuestas."}
    else:
        # Mock si el modelo no pudo cargar
        final_response = f"Respuesta unificada (Mock): {texto_parciales}"
        return {"response": final_response}

# Endpoint heredado para llamadas directas
@app.post("/infer")
async def infer_direct(req: dict):
    prompt = req.get("prompt", "")
    max_tokens = req.get("max_tokens", 384)
    temperature = req.get("temperature", 0.3)
    
    if mistral_model:
        try:
            result = mistral_model(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return {"response": result["choices"][0]["text"].strip()}
        except Exception as e:
            await log_to_logging_service("ERROR", f"Error en inferencia directa: {e}", line_num=130)
            return {"response": "Error interno del modelo"}
    return {"response": "Modelo no cargado"}

@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": mistral_model is not None}

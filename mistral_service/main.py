import asyncio
import os
import sys
import platform
import httpx
import websockets
import json
import datetime
import concurrent.futures

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from pydantic import BaseModel
from contextlib import asynccontextmanager
from huggingface_hub import InferenceClient

system = platform.system()
sys.path.append("c:/HellenCommerce") if system == "Windows" else sys.path.append("/app")
from app.utils.paths import data_path

# ============================================================
# CONFIGURACIÓN
# ============================================================
LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://bunker_logging_service:8099/ws/logs")
MODEL_PATH     = data_path("Qwen/Qwen2.5-3B-Instruct-GGUF/qwen2.5-3b-instruct-q4_k_m.gguf")
LLM_MODE       = os.getenv("LLM_MODE", "online")
# Soporta tanto HF_TOKEN (nombre oficial HuggingFace) como HF_API_KEY (alias heredado)
HF_TOKEN       = os.getenv("HF_TOKEN") or os.getenv("HF_API_KEY", "")

# llama_cpp y INFERENCE_EXECUTOR se inicializan lazy solo en modo local
mistral_model    = None
hf_client        = None
INFERENCE_EXECUTOR = None

class SynthesisRequest(BaseModel):
    partials: list[dict]

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
    global mistral_model, hf_client, INFERENCE_EXECUTOR
    
    await log_to_logging_service("INFO", "Iniciando Mistral Service para consolidar multi-intenciones", line_num=47)

    if LLM_MODE == "local":
        print(f"[Modo Local] Cargando modelo Qwen GGUF desde: {MODEL_PATH}")
        try:
            from llama_cpp import Llama  # Import lazy: solo en modo local
            INFERENCE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            mistral_model = Llama(
                model_path=MODEL_PATH,
                n_ctx=4096,
                n_threads=4,
                n_batch=256,
                use_mmap=True,
                use_mlock=False,
                chat_format=None,
                rope_freq_scale=1.0,
                verbose=True
            )
            await log_to_logging_service("INFO", f"Modelo Qwen GGUF cargado exitosamente", line_num=64)
        except Exception as e:
            await log_to_logging_service("ERROR", f"Fallo al cargar modelo Qwen GGUF: {e}", line_num=66)
    else:
        await log_to_logging_service("INFO", "Iniciando cliente HuggingFace Serverless (Modo Online) → Qwen/Qwen2.5-7B-Instruct", line_num=0)
        try:
            hf_client = InferenceClient(token=HF_TOKEN or None)
            await log_to_logging_service("INFO", "Cliente HuggingFace InferenceClient listo.", line_num=0)
        except Exception as e:
            await log_to_logging_service("ERROR", f"Fallo al cargar el cliente HF: {e}", line_num=0)

    yield
    mistral_model = None
    hf_client = None
    print("Mistral Service apagándose")

app = FastAPI(title="Mistral Unification Service", lifespan=lifespan)

@app.post("/synthesize")
async def synthesize_responses(req: SynthesisRequest):
    partials = req.partials
    
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
    
    if LLM_MODE == "local":
        if mistral_model:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    INFERENCE_EXECUTOR,
                    lambda: mistral_model(
                        prompt=prompt_mistral,
                        max_tokens=512,
                        temperature=0.3,
                        top_p=0.9
                    )
                )

                final_response = result["choices"][0]["text"].strip()
                return {"response": final_response}
            except Exception as e:
                await log_to_logging_service("ERROR", f"Error en inferencia de unificación Mistral local: {e}", line_num=107)
                return {"response": "Lo siento, tuve un problema técnico al unificar las respuestas."}
        else:
            final_response = f"Respuesta unificada (Mock): {texto_parciales}"
            return {"response": final_response}
    else:
        if hf_client:
            try:
                def call_hf():
                    response = hf_client.chat_completion(
                        model="Qwen/Qwen2.5-7B-Instruct",
                        messages=[{"role": "user", "content": prompt_mistral}],
                        max_tokens=512,
                        temperature=0.3
                    )
                    return response.choices[0].message.content.strip()

                final_response = await asyncio.to_thread(call_hf)
                return {"response": final_response}
            except Exception as e:
                await log_to_logging_service("ERROR", f"Error en inferencia HF de unificación online: {e}", line_num=0)
                return {"response": "Lo siento, tuve un problema técnico al unificar las respuestas."}
        else:
            final_response = f"Respuesta unificada (Mock): {texto_parciales}"
            return {"response": final_response}

# Endpoint heredado para llamadas directas
@app.post("/infer")
async def infer_direct(req: dict):
    prompt = req.get("prompt", "")
    max_tokens = req.get("max_tokens", 384)
    temperature = req.get("temperature", 0.3)
    top_p=req.get("top_p", 0.9)
    top_k=req.get("top_k", 40)
    repeat_penalty=req.get("repeat_penalty", 1.1)
    presence_penalty=req.get("presence_penalty", 0.0)
    echo=req.get("echo", False)
    stream=req.get("stream", False)
            
    if LLM_MODE == "local":
        if mistral_model:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    INFERENCE_EXECUTOR,
                    lambda: mistral_model(
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        top_k=top_k,
                        repeat_penalty=repeat_penalty,
                        presence_penalty=presence_penalty,
                        echo=echo,
                        stream=stream
                    )
                )

                return {"response": result["choices"][0]["text"].strip()}
            except Exception as e:
                await log_to_logging_service("ERROR", f"Error en inferencia directa local: {e}", line_num=130)
                return {"response": "Error interno del modelo"}
        return {"response": "Modelo no cargado"}
    else:
        if hf_client:
            try:
                def call_hf():
                    response = hf_client.chat_completion(
                        model="Qwen/Qwen2.5-7B-Instruct",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        temperature=temperature
                    )
                    return response.choices[0].message.content.strip()

                final_response = await asyncio.to_thread(call_hf)
                return {"response": final_response}
            except Exception as e:
                await log_to_logging_service("ERROR", f"Error en inferencia directa HF online: {e}", line_num=0)
                return {"response": "Error interno del modelo"}
        return {"response": "Modelo no cargado"}

@app.get("/health")
def health():
    if LLM_MODE == "local":
        return {"status": "ok", "mode": "local", "model_loaded": mistral_model is not None}
    else:
        return {"status": "ok", "mode": "online", "client_loaded": hf_client is not None}

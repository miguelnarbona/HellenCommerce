import asyncio
import sys

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from typing import List
from fastapi import FastAPI
from pydantic import BaseModel
from contextlib import asynccontextmanager
from llama_cpp import Llama
import os
import platform
import time
from functools import wraps

# ---------------------------------------------------------
# Lifespan context manager
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(start_up_event())
    print(f"🚀 Cragando Modelos desde HF ... on {platform.system()}")
    yield
    task.cancel()
    print("🛑 Backend apagándose, servicio de worker detenido")


app = FastAPI(
    title="Worker Service Prompt Composer",
    description="API pública que orquesta Worker_service.",
    version="2.1.0",
    lifespan=lifespan
)

llm = None

# ---------------------------------------------------------
# DECORADOR DE LOGGING
# ---------------------------------------------------------
def log_call(name: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            print(f"\n🟦 [{name}] → llamada iniciada", flush=True)
            start = time.time()

            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                print(f"🟩 [{name}] → completado en {elapsed:.3f}s", flush=True)
                return result

            except Exception as e:
                print(f"🟥 [{name}] ERROR: {e}", flush=True)
                raise e

        return wrapper
    return decorator

# ---------------------------------------------------------
# Cargar el modelo UNA SOLA VEZ
# ---------------------------------------------------------
async def start_up_event():
    global llm

    system = platform.system() 
    if  system == 'Windows':   
        MODEL_PATH = os.getenv(
            "MODEL_PATH",
            # "c:\HellenData\mistral\mistral-7b-instruct-v0.2.Q4_K_M\mistral-7b-instruct-v0.2.Q4_K_M.gguf"
            # "c:\HellenData\mistral\phi-2-instruct.Q4_K_S\phi-2-instruct.Q4_K_S.gguf"
            "c:\HellenData\Qwen\Qwen2.5-3B-Instruct-GGUF\qwen2.5-3b-instruct-q4_k_m.gguf"
        )
    else: 
        MODEL_PATH = os.getenv(
            "MODEL_PATH",
            # "/models/mistral/mistral-7b-instruct-v0.2.Q4_K_M/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
            # "/models/mistral/phi-2-instruct.Q4_K_S/phi-2-instruct.Q4_K_S.gguf"
            "/models/Qwen/Qwen2.5-3B-Instruct-GGUF/qwen2.5-3b-instruct-q4_k_m.gguf"
        )

    N_CTX = int(os.getenv("N_CTX", "2048")) # Calcular esto dinaicamente
    N_THREADS = int(os.getenv("N_THREADS", "6"))

    print(f">>> Cargando modelo Mistral .gguf desde: {MODEL_PATH}", flush=True)

    llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=N_CTX,
        n_threads=N_THREADS,
        n_batch=256, # valor anterior 256
        use_mlock=False,
        use_mmap=True,
        chat_format=None,
        rope_freq_scale=1.0,
        verbose=False
    )

    print(">>> Modelo Mistral cargado correctamente.", flush=True)

# ---------------------------------------------------------
# Esquema de petición
# ---------------------------------------------------------
class InferRequest(BaseModel):
    prompt: str
    max_tokens: int = 384     
    temperature: float = 0.3
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    presence_penalty: float = 0.0

    # Stop sequences mínimas y seguras
    # stop: List[str] = ["<STOP>"]

    echo: bool = False
 
    # 🚫 Streaming desactivado por defecto (optimizado)
    stream: bool = False

# ---------------------------------------------------------
# Servicio Paralelo
# ---------------------------------------------------------
modelo_lock = asyncio.Lock()

# ---------------------------------------------------------
# Endpoint de inferencia con logging
# ---------------------------------------------------------
@app.post("/infer")
@log_call("MISTRAL /infer")
async def infer(req: InferRequest):
    # Preprocesamiento FUERA del lock
    print(f"📥 Prompt recibido ({len(req.prompt)} chars)", flush=True)
    print(f"🔢 Tokens solicitados: {req.max_tokens}", flush=True)
    start = time.time()

    try:
        # Solo la llamada al modelo dentro del lock
        async with modelo_lock:
            result = llm(
                prompt=req.prompt,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                top_p=req.top_p,
                top_k=req.top_k,
                repeat_penalty=req.repeat_penalty,
                presence_penalty=req.presence_penalty,
                # stop=req.stop,
                echo=req.echo,
                stream=False   # 🚀 generación rápida
            )

        # Postprocesamiento FUERA del lock
        text = result["choices"][0]["text"].strip() if result else ""

        # Limpiar etiqueta <<SYS>> y <<END_SYS>> de la respuesta
        # if text.startswith("<<SYS>>"):
        #     text = text[len("<<SYS>>"):].strip()
        
        # if text.endswith("<<END_SYS>>"):
        #     text = text[:-len("<<END_SYS>>")].strip()

        gen_time = time.time() - start
        print(f"⚙️ Tiempo de generación: {gen_time:.3f}s", flush=True)
        print(f"📤 Respuesta generada ({len(text)} chars)", flush=True)

        if not text:
            return {"response": "Lo siento, no pude generar una respuesta."}

        return {"response": text}

    except Exception as e:
        print("🟥 ERROR en mistral_service /infer:", e, flush=True)
        return {"response": "Lo siento, ocurrió un error interno."}

# ---------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

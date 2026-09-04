import asyncio
import sys
import platform
import os
import re
import unicodedata
import httpx
import websockets
import json
import datetime
from huggingface_hub import InferenceClient

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from contextlib import asynccontextmanager
from pydantic import BaseModel
# llama_cpp se importa de forma lazy solo en modo local para no romper entornos cloud

# Motor semántico interno
# from intent_service.intent_semantic import detectar_intencion_semantica
from intent_semantic import detectar_intencion_semantica

# ============================================================
# CONFIGURACIÓN
# ============================================================
system = platform.system()
LOGGING_WS_URL = os.getenv("LOGGING_WS_URL", "ws://bunker_logging_service:8099/ws/logs")
sys.path.append("c:/HellenCommerce") if system == "Windows" else sys.path.append("/app")
from app.utils.paths import hc_path, data_path
BASE_RES = hc_path("app/resources")
MODEL_PATH_ULT = data_path("mistral/mistral-7b-instruct-v0.2.Q4_K_M/mistral-7b-instruct-v0.2.Q4_K_M.gguf")

LLM_MODE = os.getenv("LLM_MODE", "online")
# Soporta tanto HF_TOKEN (nombre oficial HuggingFace) como HF_API_KEY (alias heredado)
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HF_API_KEY", "")

KEYWORDS_FILES = {
    "COMPRA": "keywords_buy.txt",
    "VENTA": "keywords_sel.txt",
    "NOTIFICACION": "keywords_ntfy.txt",
    "MENSAJERIA": "keywords_msg.txt",
    "TRANSPORTE": "keywords_transport.txt",
    "INFORMATIVA": "keywords_info.txt",
    "OTRA": "keywords_other.txt"
}

class InputText(BaseModel):
    message: str
    mercancia: str | None = None
    contexto: str | None = None

# ============================================================
# LOGGING AL LOGGING_SERVICE
# ============================================================
async def log_to_logging_service(level: str, msg: str, status_flag="SOLUCIONADO", line_num=0):
    try:
        async with websockets.connect(LOGGING_WS_URL) as ws:
            payload = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "log_level": level,
                "service_origin": "intent_service",
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
        print(f"[DEBUG] Error enviando log: {e}")

# ============================================================
# 1. Cargar KEYWORDS_BASE desde archivo
# ============================================================
def cargar_keywords_base(path):
    base = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                kw = line.strip().lower()
                if not kw:
                    continue
                if "{mercancia}" in kw:
                    fijo = kw.split("{")[0].strip()
                    if fijo:
                        base.append(fijo)
                else:
                    base.append(kw)
    except Exception as e:
        print(f"[ERROR] No se pudo cargar {path}: {e}")
    return list(dict.fromkeys(base))

# ============================================================
# 2. Detección por keywords (fallback)
# ============================================================
def detectar_intencion_keywords(mensaje, KEYWORDS_BASE_MAP):
    msg = mensaje.lower().strip()
    intenciones = []
    for categoria, base_list in KEYWORDS_BASE_MAP.items():
        for kw in base_list:
            patron = r"\b" + re.escape(kw).replace(r"\ ", r"\s+") + r"\b"
            if re.search(patron, msg):
                if categoria not in intenciones:
                    intenciones.append(categoria)
                break
    if not intenciones:
        return ["OTRA"]
    return intenciones

KEYWORDS_BASE_MAP = {
    categoria: cargar_keywords_base(os.path.join(BASE_RES, archivo))
    for categoria, archivo in KEYWORDS_FILES.items()
}

# ============================================================
# 4. FastAPI + Modelo LLM
# ============================================================
intent_llm = None
hf_client = None
modelo_lock = asyncio.Lock()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global intent_llm, hf_client
    
    if LLM_MODE == "local":
        await log_to_logging_service("INFO", "Bootstrapping intent_service: Iniciando carga de modelo GGUF (Modo Local)", line_num=0)
        try:
            from llama_cpp import Llama  # Import lazy: solo en modo local
            intent_llm = Llama(
                model_path=MODEL_PATH_ULT,
                n_ctx=1500,
                n_threads=4,
                n_batch=256,
                use_mmap=True,
                use_mlock=False,
                verbose=True
            )
            await log_to_logging_service("INFO", f"Modelo GGUF cargado exitosamente desde {MODEL_PATH_ULT}", line_num=0)
        except Exception as e:
            await log_to_logging_service("ERROR", f"Fallo al cargar el modelo GGUF: {e}", line_num=0)
    else:
        await log_to_logging_service("INFO", "Bootstrapping intent_service: Iniciando cliente HF Serverless (Modo Online)", line_num=0)
        try:
            hf_client = InferenceClient(token=HF_TOKEN or None)
            await log_to_logging_service("INFO", "Cliente HuggingFace InferenceClient inicializado → mistralai/Mistral-7B-Instruct-v0.2", line_num=0)
        except Exception as e:
            await log_to_logging_service("ERROR", f"Fallo al cargar cliente HF: {e}", line_num=0)

    yield
    intent_llm = None
    hf_client = None
    print(">>> Intent Service apagándose.")

app = FastAPI(title="Intent Detection Service", lifespan=lifespan)

# ============================================================
# 5. Endpoint principal
# ============================================================
@app.post("/intent")
async def infer_intencion(input: InputText):
    mensaje = input.message
    contexto = input.contexto or ""
    mercancia = input.mercancia or ""

    print(f"[DEBUG] Recibido: mensaje='{mensaje[:50]}...' contexto='{contexto[:50]}...'")
    
    prompt_mistral = f"""
        [INST] Actúa como un broker profesional de comercio. Tu responsabilidad es determinar si el usuario quiere COMPRAR, VENDER o solicitar información.
        Interpreta SOLO el ÚLTIMO mensaje para descubrir la intención actual.
        REGLA CRÍTICA: 
        - Si el usuario pregunta "¿tienes X?", "¿vendes X?" o "¿tendrás X a la venta?", su intención es COMPRAR (él es el comprador).
        - Si el usuario dice "vendo X", "ofrezco X" o "tengo X para vender", su intención es VENDER (él es el vendedor).
        - Las preguntas sobre disponibilidad, stock o existencia son siempre INFORMATIVA.
        
        Categorías válidas: COMPRA, VENTA, SERVICIO, MENSAJERIA, TRANSPORTE, INFORMATIVA, NEGOCIO, NOTIFICACION, SALUDOS, CONTACTO, RUTA.

        Ejemplos:
        - "dame el contacto de un vendedor cercano" -> CONTACTO
        - "Necesito comprar arroz" -> COMPRA
        - "Hola, tendras arroz a la venta?" -> COMPRA, INFORMATIVA
        - "¿Tienes disponibilidad de maíz?" -> COMPRA, INFORMATIVA
        - "Quiero vender mi cosecha" -> VENTA
        - "¿A cómo está el kilo de papa?" -> INFORMATIVA
        - "Avisame cuando llegue stock" -> NOTIFICACION
        - "Hola" -> SALUDOS
        - "quiero comprar y que me lo envíen" -> COMPRA, MENSAJERIA
        - "¿Me das el teléfono del local?" -> CONTACTO
        - "¿Cómo llego al vendedor Yanet González?" -> RUTA, INFORMATIVA
        - "Puedes decirme cómo llego al vendedor?" -> RUTA, INFORMATIVA
        - "¿Cuál es la ruta hacia la tienda?" -> RUTA, INFORMATIVA

        Responde SOLAMENTE con las categorías exactas, separadas por coma.
        [/INST]
    """
    if contexto:
        prompt_mistral += f"\n    Contexto conversacional previo:\n    {contexto}\n"
    prompt_mistral += f"\n    ÚLTIMO Mensaje del usuario a clasificar: \"{mensaje}\"\n    [/INST]"

    intenciones_modelo = []
    valid_options = {"COMPRA","VENTA","SERVICIO","MENSAJERIA","TRANSPORTE","INFORMATIVA","NEGOCIO","NOTIFICACION","SALUDOS","CONTACTO","RUTA","OTRA"}
    
    if LLM_MODE == "local":
        if intent_llm:
            async with modelo_lock:
                try:
                    result = await asyncio.to_thread(
                        intent_llm,
                        prompt=prompt_mistral, 
                        max_tokens=32, 
                        temperature=0.0, 
                        top_p=1.0, 
                        top_k=1
                    )
                    
                    raw_model_output = result["choices"][0]["text"].strip().upper()
                    modelo_tokens = re.findall(r"[A-Z]+", raw_model_output)
                    
                    for token in modelo_tokens:
                        if token in valid_options and token not in intenciones_modelo:
                            intenciones_modelo.append(token)
                except Exception as e:
                    await log_to_logging_service("ERROR", f"Error en inferencia LLM local: {e}", line_num=0)
                    print(f"[ERROR] Inferencia LLM falló: {e}")
    else:
        if hf_client:
            try:
                def call_hf():
                    response = hf_client.chat_completion(
                        model="mistralai/Mistral-7B-Instruct-v0.2",
                        messages=[{"role": "user", "content": prompt_mistral}],
                        max_tokens=32,
                        temperature=0.0,
                    )
                    return response.choices[0].message.content.strip()

                raw_model_output = await asyncio.to_thread(call_hf)
                raw_model_output = raw_model_output.upper()
                modelo_tokens = re.findall(r"[A-Z]+", raw_model_output)
                
                for token in modelo_tokens:
                    if token in valid_options and token not in intenciones_modelo:
                        intenciones_modelo.append(token)
            except Exception as e:
                await log_to_logging_service("ERROR", f"Error en inferencia HF online: {e}", line_num=0)
                print(f"[ERROR] Inferencia HF falló: {e}")

    if not intenciones_modelo:
        # Fallbacks
        try:
            intenciones_semanticas = detectar_intencion_semantica(mensaje)
            valid_semanticas = [i for i in intenciones_semanticas if i in valid_options]
            
            if valid_semanticas:
                intenciones_modelo = valid_semanticas
            else:
                intenciones_modelo = detectar_intencion_keywords(mensaje, KEYWORDS_BASE_MAP)
                valid_kw = [i for i in intenciones_modelo if i in valid_options]
                intenciones_modelo = valid_kw if valid_kw else ["OTRA"]
        except Exception as e:
            await log_to_logging_service("ERROR", f"Error en fallback semántico: {e}", line_num=0)
            intenciones_modelo = ["OTRA"]

    # Post-proceso navegación
    msg_norm = re.sub(r"[\u0300-\u036f]", "", unicodedata.normalize("NFD", mensaje.lower()))
    if re.search(r"\b(como llego|como llegar|llegar al|indicaciones|ruta|trazar|donde queda)\b", msg_norm):
        if "CONTACTO" in intenciones_modelo:
            intenciones_modelo = [i for i in intenciones_modelo if i != "CONTACTO"]
        if "RUTA" not in intenciones_modelo:
            intenciones_modelo.append("RUTA")
        if "INFORMATIVA" not in intenciones_modelo:
            intenciones_modelo.append("INFORMATIVA")

    if not intenciones_modelo:
        intenciones_modelo = ["OTRA"]

    return {"intent": intenciones_modelo[0], "intents": intenciones_modelo}

@app.get("/health")
def health():
    return {"status": "ok"}

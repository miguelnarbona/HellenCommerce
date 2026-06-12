import asyncio
import sys

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from contextlib import asynccontextmanager
from pydantic import BaseModel
from llama_cpp import Llama
import os
import re
import platform

# Motor semántico interno
from intent_service.intent_semantic import detectar_intencion_semantica

class InputText(BaseModel):
    mensaje: str
    mercancia: str | None = None 
    contexto: str | None = None  # COPILOT-add: Contexto previo para mejorar detección

# ---------------------------------------------------------
# Esquema de petición
# ---------------------------------------------------------
class InferRequest(BaseModel):
    prompt: str
    max_tokens: int = 160
    temperature: float = 0.65
    top_p: float = 0.85
    top_k: float = 40
    stop: str = ["</s>"]
    echo: bool = False
    stream: bool = False

# ============================================================
# CONFIGURACIÓN
# ============================================================

system = platform.system()

KEYWORDS_FILES = {
    "COMPRA": "keywords_buy.txt",
    "VENTA": "keywords_sel.txt",
    "NOTIFICACION": "keywords_ntfy.txt",
    "MENSAJERIA": "keywords_msg.txt",
    "TRANSPORTE": "keywords_transport.txt",
    "INFORMATIVA": "keywords_info.txt",
    "OTRA": "keywords_other.txt"
}

BASE_RES = (
    "c:/HellenCommerce/app/resources"
    if system == "Windows"
    else "app/resources"
)


# ============================================================
# 1. Cargar KEYWORDS_BASE desde archivo
# ============================================================

def cargar_keywords_base(path):
    base = []
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
    return list(dict.fromkeys(base))


# ============================================================
# 2. Detección por keywords (fallback)
# ============================================================

def detectar_intencion_keywords(mensaje, KEYWORDS_BASE_MAP):
    msg = mensaje.lower().strip()

    for categoria, base_list in KEYWORDS_BASE_MAP.items():
        for kw in base_list:
            patron = r"\b" + re.escape(kw).replace(r"\ ", r"\s+") + r"\b"
            if re.search(patron, msg):
                return categoria

    return "OTRA"

# ============================================================
# 3. Cargar todas las KEYWORDS_BASE
# ============================================================

KEYWORDS_BASE_MAP = {
    categoria: cargar_keywords_base(os.path.join(BASE_RES, archivo))
    for categoria, archivo in KEYWORDS_FILES.items()
}

# ============================================================
# 4. FastAPI + Modelo LLM
# ============================================================

intent_llm = None
modelo_lock = asyncio.Lock()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global intent_llm

    system = platform.system()
    if system == "Windows":
        MODEL_PATH_ULT = os.getenv(
            "MODEL_PATH_ULT",
            "c:/HellenData/mistral/mistral-7b-instruct-v0.2.Q4_K_M/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
            # "c:/HellenData/Qwen/Qwen2.5-3B-Instruct-GGUF/qwen2.5-3b-instruct-q4_k_m.gguf"
        )
    else:
        MODEL_PATH_ULT = os.getenv(
            "MODEL_PATH_ULT",
            "/models/mistral/mistral-7b-instruct-v0.2.Q4_K_M/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
            # "/models/Qwen/Qwen2.5-3B-Instruct-GGUF/qwen2.5-3b-instruct-q4_k_m.gguf"
        )

    intent_llm = Llama(
        model_path=MODEL_PATH_ULT,
        n_ctx=1024,
        n_threads=4,
        n_batch=256,
        use_mmap=True,
        use_mlock=False
    )

    print(">>> Modelo de intención cargado correctamente.")
    yield
    intent_llm = None


app = FastAPI(lifespan=lifespan)


# ============================================================
# 5. Endpoint principal
# ============================================================

@app.post("/infer_intencion")
async def infer_intencion(input: InputText):
    mensaje = input.mensaje
    contexto = input.contexto or ""  # Contexto previo opcional
    mercancia = input.mercancia or ""

    print(f"[DEBUG] Recibido: mensaje='{mensaje[:50]}...' contexto='{contexto[:50]}...'")
    
    # Inicializar con valor por defecto
    intencion_modelo = "OTRA"

    # 1. Modelo como método principal: interpretar la solicitud completa
    #    y forzar la clasificación de la intención a una categoría válida.
    prompt_mistral = f"""
    [INST] Eres un profesional de los NEGOCIOS con agudeza para determinar las necesidades de las personas.
    Interpreta el mensaje del usuario para descubrir cuál es su intención o necesidad principal.
    Debes clasificar la necesidad ESTRICTAMENTE en UNA de las siguientes categorías:
    COMPRA, VENTA, SERVICIO, MENSAJERIA, TRANSPORTE, INFORMATIVA, NEGOCIO, NOTIFICACION, SALUDOS, CONTACTO.

    Ejemplos:
    - "dame el contacto de un vendedor cercano" -> CONTACTO
    - "pásame el número" -> CONTACTO
    - "Necesito comprar producto en volumen" -> COMPRA
    - "Tendras arroz a la venta?" -> COMPRA
    - "tienes frijol?" -> COMPRA
    - "Tendras algo frio?" -> COMPRA
    - "Quiero vender mi mercancía a mayoreo" -> VENTA
    - "Ofrezco 5 toneladas de azúcar" -> VENTA
    - "¿Cuál es el precio del tomate?" -> INFORMATIVA
    - "Envíame el producto mañana" -> MENSAJERIA
    - "¿Puedes conseguir transporte para la carga?" -> TRANSPORTE
    - "Avisame cuando haya" -> NOTIFICACION
    - "Puedes notificarme ?" -> NOTIFICACION
    - "Hola, buenos días" -> SALUDOS
    - "Busco oportunidad de negocio" -> NEGOCIO

    Responde SOLAMENTE con la palabra de la categoría exacta. No incluyas signos de puntuación ni explicaciones adicionales.

    Mensaje del usuario: "{mensaje}"\n"""

    if contexto:
        prompt_mistral += f"Contexto conversacional previo: {contexto}\n"

    prompt_mistral += "[/INST]"

    async with modelo_lock:
        result = intent_llm(
            prompt=prompt_mistral,
            max_tokens=16,
            temperature=0.0,
            top_p=1.0,
            top_k=1
        )

    raw_model_output = result["choices"][0]["text"].strip().upper()
    modelo_tokens = re.findall(r"[A-Z]+", raw_model_output)
    intencion_modelo = modelo_tokens[0] if modelo_tokens else raw_model_output
    print(f"[DEBUG] Intención detectada por modelo: {intencion_modelo} (raw={raw_model_output})")

    valid_options = {"COMPRA","VENTA","SERVICIO","MENSAJERIA","TRANSPORTE","INFORMATIVA","NEGOCIO","NOTIFICACION","SALUDOS","CONTACTO"}

    if intencion_modelo not in valid_options:
        print(f"[DEBUG] Modelo devolvió valor inválido: {intencion_modelo}")

        # 2. Fallback semántico si el modelo no devuelve una categoría válida.
        intencion_semantica = detectar_intencion_semantica(mensaje)
        print(f"[DEBUG] Intento fallback semántico: {intencion_semantica}")

        if intencion_semantica in valid_options:
            intencion_modelo = intencion_semantica
            print(f"[DEBUG] Fallback semántico usado: {intencion_modelo}")
        else:
            intencion_modelo = detectar_intencion_keywords(mensaje, KEYWORDS_BASE_MAP)
            print(f"[DEBUG] Fallback keywords usado: {intencion_modelo}")
            if intencion_modelo not in valid_options:
                intencion_modelo = "OTRA"

    print(f"[DEBUG] Intención final retornada: {intencion_modelo}")
    return {"intencion": intencion_modelo}
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
import unicodedata  # CURSOR-add: normalizar mensaje en post-proceso de navegación

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
    intenciones = []

    for categoria, base_list in KEYWORDS_BASE_MAP.items():
        for kw in base_list:
            patron = r"\b" + re.escape(kw).replace(r"\ ", r"\s+") + r"\b"
            if re.search(patron, msg):
                if categoria not in intenciones:
                    intenciones.append(categoria)
                break # Encontramos al menos una kw para esta categoría

    if not intenciones:
        return ["OTRA"]
    return intenciones

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
        n_ctx=1500, # A medida que la RAM se incremente este parametro debe subir
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
    [INST] Actúa como un broker profesional de comercio. Tu responsabilidad es determinar si el usuario quiere COMPRAR, VENDER o solicitar información.
    Interpreta SOLO el ÚLTIMO mensaje para descubrir la intención actual.
    REGLA CRÍTICA: 
    - Si el usuario pregunta "¿tienes X?", "¿vendes X?" o "¿tendrás X a la venta?", su intención es COMPRAR (él es el comprador).
    - Si el usuario dice "vendo X", "ofrezco X" o "tengo X para vender", su intención es VENDER (él es el vendedor).
    - Las preguntas sobre disponibilidad, stock o existencia son siempre INFORMATIVA.
    
    Categorías válidas: COMPRA, VENTA, SERVICIO, MENSAJERIA, TRANSPORTE, INFORMATIVA, NEGOCIO, NOTIFICACION, SALUDOS, CONTACTO.

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
    - "¿Cómo llego al vendedor Yanet González?" -> INFORMATIVA
    - "Puedes decirme cómo llego al vendedor?" -> INFORMATIVA
    - "¿Cuál es la ruta hacia la tienda?" -> INFORMATIVA

    Responde SOLAMENTE con las categorías exactas, separadas por coma.
    [/INST]
"""

    if contexto:
        prompt_mistral += f"\n    Contexto conversacional previo:\n    {contexto}\n"

    prompt_mistral += f"\n    ÚLTIMO Mensaje del usuario a clasificar: \"{mensaje}\"\n    [/INST]"

    async with modelo_lock:
        result = intent_llm(
            prompt=prompt_mistral,
            max_tokens=32,
            temperature=0.0,
            top_p=1.0,
            top_k=1
        )

    raw_model_output = result["choices"][0]["text"].strip().upper()
    modelo_tokens = re.findall(r"[A-Z]+", raw_model_output)
    
    valid_options = {"COMPRA","VENTA","SERVICIO","MENSAJERIA","TRANSPORTE","INFORMATIVA","NEGOCIO","NOTIFICACION","SALUDOS","CONTACTO"}
    
    intenciones_modelo = []
    for token in modelo_tokens:
        if token in valid_options and token not in intenciones_modelo:
            intenciones_modelo.append(token)
            
    print(f"[DEBUG] Intención(es) detectada(s) por modelo: {intenciones_modelo} (raw={raw_model_output})")

    if not intenciones_modelo:
        print(f"[DEBUG] Modelo no devolvió valores válidos.")

        # 2. Fallback semántico
        intenciones_semanticas = detectar_intencion_semantica(mensaje)
        print(f"[DEBUG] Intento fallback semántico: {intenciones_semanticas}")

        valid_semanticas = [i for i in intenciones_semanticas if i in valid_options]
        
        if valid_semanticas:
            intenciones_modelo = valid_semanticas
            print(f"[DEBUG] Fallback semántico usado: {intenciones_modelo}")
        else:
            # 3. Fallback por palabras
            intenciones_modelo = detectar_intencion_keywords(mensaje, KEYWORDS_BASE_MAP)
            print(f"[DEBUG] Fallback keywords usado: {intenciones_modelo}")
            valid_kw = [i for i in intenciones_modelo if i in valid_options]
            if not valid_kw:
                intenciones_modelo = ["OTRA"]
            else:
                intenciones_modelo = valid_kw

    # CURSOR-add: post-proceso navegación — no clasificar "cómo llego" como CONTACTO
    msg_norm = re.sub(
        r"[\u0300-\u036f]", "",
        unicodedata.normalize("NFD", mensaje.lower())
    )
    if re.search(r"\b(como llego|como llegar|llegar al|indicaciones|ruta|trazar|donde queda)\b", msg_norm):
        if "CONTACTO" in intenciones_modelo:
            intenciones_modelo = [i for i in intenciones_modelo if i != "CONTACTO"]
            print("[DEBUG] CURSOR: CONTACTO eliminado por frase de navegación", flush=True)
        if "INFORMATIVA" not in intenciones_modelo:
            intenciones_modelo.append("INFORMATIVA")

    print(f"[DEBUG] Intención final retornada: {intenciones_modelo}")
    # Retornamos la primera intención principal para retrocompatibilidad,
    # pero también enviamos la lista completa de intenciones.
    return {"intencion": intenciones_modelo[0], "intenciones": intenciones_modelo}
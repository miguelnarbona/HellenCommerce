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

class InputText(BaseModel):
    mensaje: str


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
# 1. Cargar KEYWORDS_BASE desde archivo (sin {MERCANCIA})
# ============================================================

def cargar_keywords_base(path):
    """
    Carga todas las keywords desde archivo y extrae la parte fija,
    eliminando el token {MERCANCIA}.
    """
    base = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            kw = line.strip().lower()
            if not kw:
                continue

            # Si contiene {MERCANCIA}, tomar solo la parte fija
            if "{mercancia}" in kw or "{MERCANCIA}" in kw:
                fijo = kw.split("{")[0].strip()
                if fijo:
                    base.append(fijo)
            else:
                base.append(kw)

    # Eliminar duplicados
    return list(dict.fromkeys(base))


# ============================================================
# 2. Construir regex general para detectar keyword + palabra siguiente
# ============================================================

def construir_regex_keywords_base(KEYWORDS_BASE):
    """
    Construye un regex que detecta:
        <keyword_base> <palabra_siguiente>
    donde palabra_siguiente es candidata a MERCANCIA.
    """

    patrones = [
        re.escape(kw).replace(r"\ ", r"\s+")
        for kw in KEYWORDS_BASE
    ]

    regex = r"\b(" + "|".join(patrones) + r")\b\s+([a-záéíóúñ]+)"
    return re.compile(regex, re.IGNORECASE)


# ============================================================
# 3. Detectar keyword base + mercancía
# ============================================================

def detectar_keyword_y_mercancia(mensaje, KEYWORDS_BASE, regex):
    msg = mensaje.lower()

    m = regex.search(msg)
    if not m:
        return None, None

    keyword = m.group(1).strip()
    palabra = m.group(2).strip()

    # Si la palabra siguiente NO es otra keyword base → es mercancía
    if palabra not in KEYWORDS_BASE:
        return keyword, palabra

    return keyword, None


# ============================================================
# 4. Detectar intención por keywords (todas las categorías)
# ============================================================

def detectar_intencion_keywords(mensaje, KEYWORDS_BASE_MAP, REGEX_MAP):
    """
    Detecta intención usando keywords base para TODAS las categorías.
    COMPRA y VENTA usan lógica inteligente keyword_base + palabra_siguiente.
    El resto usa coincidencia directa de keyword base.
    """
    msg = mensaje.lower().strip()

    # 1. COMPRA (lógica inteligente)
    keyword, mercancia = detectar_keyword_y_mercancia(
        msg,
        KEYWORDS_BASE_MAP["COMPRA"],
        REGEX_MAP["COMPRA"]
    )
    if keyword and mercancia:
        return "COMPRA"

    # 2. VENTA (misma lógica inteligente)
    keyword, mercancia = detectar_keyword_y_mercancia(
        msg,
        KEYWORDS_BASE_MAP["VENTA"],
        REGEX_MAP["VENTA"]
    )
    if keyword and mercancia:
        return "VENTA"

    # 3. Otras categorías: coincidencia directa
    for categoria, base_list in KEYWORDS_BASE_MAP.items():
        if categoria in ("COMPRA", "VENTA"):
            continue

        for kw in base_list:
            patron = r"\b" + re.escape(kw).replace(r"\ ", r"\s+") + r"\b"
            if re.search(patron, msg):
                return categoria

    return "OTRA"

# ============================================================
# 5. Cargar todas las KEYWORDS_BASE por categoría
# ============================================================

KEYWORDS_BASE_MAP = {
    categoria: cargar_keywords_base(os.path.join(BASE_RES, archivo))
    for categoria, archivo in KEYWORDS_FILES.items()
}

# Regex especial para COMPRA
REGEX_COMPRA = construir_regex_keywords_base(KEYWORDS_BASE_MAP["COMPRA"])


# ============================================================
# 6. FastAPI + Modelo LLM
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
            "c:/HellenData/Qwen/Qwen2.5-3B-Instruct-GGUF/qwen2.5-3b-instruct-q4_k_m.gguf"
        )
    else:
        MODEL_PATH_ULT = os.getenv(
            "MODEL_PATH_ULT",
            "/models/Qwen/Qwen2.5-3B-Instruct-GGUF/qwen2.5-3b-instruct-q4_k_m.gguf"
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
# 7. Endpoint principal
# ============================================================

@app.post("/infer_intencion")
async def infer_intencion(input: InputText):

    # 1. Intención por keywords
    intencion_keywords = detectar_intencion_keywords(
        input.mensaje,
        KEYWORDS_BASE_MAP,
        REGEX_COMPRA
    )

    # 2. Intención por modelo
    prompt = f"""
    <<SYS>>
    Clasifica el mensaje del usuario en UNA SOLA de estas categorías:
    COMPRA, VENTA, SERVICIO, INFORMACION, NEGOCIO, CONTACTO,
    MENSAJERIA, NOTIFICACION, SALUDO, TRANSPORTE, DESPEDIDA, OTRA.

    REGLAS ABSOLUTAS:
    - Responde SOLO con una palabra.
    - No expliques nada.
    - No agregues texto adicional.
    <<END_SYS>>
    <<USR>>
    MENSAJE DEL USUARIO:
    "{input.mensaje}"
    RESPUESTA:
    <<END_USR>>
    """

    async with modelo_lock:
        result = intent_llm(
            prompt,
            max_tokens=4,
            temperature=0.0,
            top_p=1.0,
            stop=["\n"],
            echo=False
        )

    intencion_modelo = result["choices"][0]["text"].strip().upper()

    categorias = [
        "COMPRA","VENTA","SERVICIO","INFORMACION","NEGOCIO","CONTACTO",
        "MENSAJERIA","NOTIFICACION","SALUDO","TRANSPORTE","DESPEDIDA","OTRA"
    ]

    if intencion_modelo not in categorias:
        intencion_modelo = "OTRA"

    # 3. Comparación
    if intencion_keywords == intencion_modelo:
        return {"intencion": intencion_modelo}

    # 4. Desacuerdo → pedir aclaración
    return {"intencion": "ACLARAR_INTENCION"}

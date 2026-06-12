from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Depends, HTTPException, Header
from firebase_admin import auth as firebase_auth
import firebase_admin
from firebase_admin import credentials
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, Depends
import httpx
import os
import re
import platform
import asyncio
import json
import sqlite3
import datetime

from app.core.pipeline.PromptBuilder import PromptBuilder
from app.core.pipeline.PromptReducer import PromptReducer
from app.core.pipeline.PromptCnfReducer import PromptCnfReducer
from app.core.pipeline.PromptReducerUltra import PromptReducerUltra

cred = credentials.Certificate(
    r"C:\HellenCommerce\fastapi_service\firebase-admin.json"
)
firebase_admin.initialize_app(cred)

app = FastAPI(
    title="IA Broker Multicanal",
    description="API pública que orquesta worker_service + mistral_service + HF.",
    version="2.1.0"
)

# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# URLs de servicios internos
# ---------------------------------------------------------
system = platform.system()

if system == "Windows":
    WORKER_URL = os.getenv("WORKER_URL")
    MISTRAL_URL = os.getenv("MISTRAL_URL")
else:
    WORKER_URL = os.getenv("WORKER_URL", "http://worker_service:9000")
    MISTRAL_URL = os.getenv("MISTRAL_URL", "http://mistral_service:9001")

HF_API_KEY = os.getenv("HF_API_KEY", "")

# ---------------------------------------------------------
# Carga de keywords desde ficheros
# ---------------------------------------------------------
def cargar_keywords(path: str) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]
    except Exception:
        return []

BASE_RES = f"c:/HellenCommerce/app/resources" if system == "Windows" else "app/resources"

KEYWORDS_BUY       = cargar_keywords(os.path.join(BASE_RES, "keywords_buy.txt"))
KEYWORDS_SELL      = cargar_keywords(os.path.join(BASE_RES, "keywords_sel.txt"))
KEYWORDS_NTFY      = cargar_keywords(os.path.join(BASE_RES, "keywords_ntfy.txt"))
KEYWORDS_MSG       = cargar_keywords(os.path.join(BASE_RES, "keywords_msg.txt"))
KEYWORDS_TRANSPORT = cargar_keywords(os.path.join(BASE_RES, "keywords_transport.txt"))
KEYWORDS_INFO      = cargar_keywords(os.path.join(BASE_RES, "keywords_info.txt"))
KEYWORDS_OTHER     = cargar_keywords(os.path.join(BASE_RES, "keywords_other.txt"))

# ---------------------------------------------------------
# Modelos de entrada
# ---------------------------------------------------------
class UserMessage(BaseModel):
    user_id: str
    conversation_id: int | None = None
    message: str

class NotificacionLeida(BaseModel):
    notif_id: int
    user_id: str

class NewConversation(BaseModel):
    user_id: str

class NewMessage(BaseModel):
    conversation_id: int
    user_id: str
    rol: str
    contenido: str

class ProductCreate(BaseModel):
    user_id: str
    name: str
    price: float
    description: str | None = None
    image: str | None = None

# ---------------------------------------------------------
# DB Helpers
# ---------------------------------------------------------
def get_db():
    conn = sqlite3.connect(
        os.getenv("SQLITE_PATH"), 
        check_same_thread=False
        )
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------------------------------------
# Fallback HuggingFace
# ---------------------------------------------------------
async def fallback_hf(prompt: str) -> str:
    url = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}

    async with httpx.AsyncClient(timeout=600.0) as client:
        r = await client.post(url, headers=headers, json={"inputs": prompt})
        try:
            data = r.json()
            if isinstance(data, list) and "generated_text" in data[0]:
                return data[0]["generated_text"]
        except Exception:
            pass

    return "Lo siento, hubo un error generando la respuesta."

# ---------------------------------------------------------
# DETECTOR DE ESTADOS
# ---------------------------------------------------------
def detectar_estado(mensaje: str, contexto: list[str]):
    msg = mensaje.lower().strip()

    # Estado 2: usuario confirma gestión
    intenciones_gestion = [
        "gestionalo", "hazlo tú", "hazlo en mi lugar", "encárgate",
        "gestionarlo", "hazlo por mi", "hazlo por mí",
        "si, gestionalo", "sí, gestionalo", "si gestionalo", "sí gestionalo",
        "si hazlo", "sí hazlo", "hazlo"
    ]

    if any(x in msg for x in intenciones_gestion):
        return "STATE_CONFIRMACION"

    # Estado 1: usuario pide producto (nueva intención de compra)
    if any(k in msg for k in KEYWORDS_BUY):
        return "STATE_PRODUCTO"

    return "STATE_OTRO"

# ---------------------------------------------------------
# FILTRAR VENDEDORES
# ---------------------------------------------------------
def filtrar_vendedores(content: list[dict]):
    """
    Filtro robusto para vendedores reales:
    - Acepta vendedores aunque falte precio o ubicación.
    - Rechaza nombres genéricos o inventados.
    - Rechaza mercancías irreales o generadas por el modelo.
    - Mantiene fallback si no hay válidos.
    """

    if not content:
        return [], []

    validos = []
    basura = []

    nombres_invalidos = {
        "", "nombre", "vendedor genérico", "usuario", "cliente",
        "persona", "alguien", "desconocido"
    }

    mercancias_invalidas = {
        "", "puede", "hola", "gracias", "ninguna", "no se",
        "servicio", "producto", "artículo"
    }

    for item in content:
        tipo = (item.get("tipo") or "").strip().lower()
        nombre = (item.get("nombre") or "").strip().lower()
        merc = (item.get("mercancia") or "").strip().lower()

        if tipo != "vendedor":
            basura.append(item)
            continue

        nombre_invalido = (
            nombre in nombres_invalidos or
            len(nombre) < 3 or
            nombre.isdigit()
        )

        merc_invalida = (
            merc in mercancias_invalidas or
            len(merc) < 3 or
            merc.isdigit()
        )

        if nombre == "vendedor" and not merc_invalida:
            validos.append(item)
            continue

        es_valido = not nombre_invalido and not merc_invalida

        if es_valido:
            validos.append(item)
        else:
            basura.append(item)

    if validos:
        return validos, basura

    return [], basura

# ---------------------------------------------------------
# FILTRAR COMPRADORES
# ---------------------------------------------------------
def filtrar_compradores(content: list[dict]):
    """
    Filtro robusto para vendedores reales:
    - Acepta vendedores aunque falte precio o ubicación.
    - Rechaza nombres genéricos o inventados.
    - Rechaza mercancías irreales o generadas por el modelo.
    - Mantiene fallback si no hay válidos.
    """

    if not content:
        return [], []

    validos = []
    basura = []

    nombres_invalidos = {
        "", "nombre", "comprador genérico", "usuario", "cliente",
        "persona", "alguien", "desconocido"
    }

    mercancias_invalidas = {
        "", "puede", "hola", "gracias", "ninguna", "no se",
        "servicio", "producto", "artículo"
    }

    for item in content:
        tipo = (item.get("tipo") or "").strip().lower()
        nombre = (item.get("nombre") or "").strip().lower()
        merc = (item.get("mercancia") or "").strip().lower()

        if tipo != "comprador":
            basura.append(item)
            continue

        nombre_invalido = (
            nombre in nombres_invalidos or
            len(nombre) < 3 or
            nombre.isdigit()
        )

        merc_invalida = (
            merc in mercancias_invalidas or
            len(merc) < 3 or
            merc.isdigit()
        )

        if nombre == "comprador" and not merc_invalida:
            validos.append(item)
            continue

        es_valido = not nombre_invalido and not merc_invalida

        if es_valido:
            validos.append(item)
        else:
            basura.append(item)

    if validos:
        return validos, basura

    return [], basura

# ---------------------------------------------------------
# ACTUALIZAR MERCANCÍA (MEMORIA SEMÁNTICA)
# ---------------------------------------------------------
def actualizar_mercancia(message: str, current_query: str | None):
    msg = message.strip().lower()

    # 1. Si es mensajería, transporte, info, notificación → NO tocar mercancía
    if (
        any(k in msg for k in KEYWORDS_MSG) or
        any(k in msg for k in KEYWORDS_TRANSPORT) or
        any(k in msg for k in KEYWORDS_INFO) or
        any(k in msg for k in KEYWORDS_NTFY)
    ):
        return current_query

    # 2. Si es compra → resetear mercancía
    if any(k in msg for k in KEYWORDS_BUY):
        return message

    # 3. Si es venta → NO modificar mercancía
    if any(k in msg for k in KEYWORDS_SELL):
        return current_query

    # 4. Detectar modelos reales
    patron_modelo = r"\b([a-zA-Z]{1,4}\d{1,4}|[0-9]{2,3}w|[0-9]{1,2}\")\b"
    match = re.search(patron_modelo, msg, re.IGNORECASE)

    if match:
        modelo = match.group(0)
        if current_query:
            if modelo.lower() not in current_query.lower():
                return f"{current_query} {modelo}".strip()
            return current_query
        else:
            return modelo

    # 5. Refinamientos válidos
    refinamientos = [
        "color", "rojo", "azul", "negro", "blanco",
        "pulgadas", "inch", "marca", "recargable"
    ]

    if any(w in msg for w in refinamientos):
        if current_query:
            if msg not in current_query.lower():
                return f"{current_query} {msg}".strip()
            return current_query
        else:
            return msg

    # 6. Frases irrelevantes
    irrelevantes = {
        "ok", "dale", "si", "sí", "puede ser", "claro", "perfecto",
        "está bien", "bien", "ok dale", "ok gracias", "gracias"
    }

    if msg in irrelevantes:
        return current_query

    # 7. Default
    return current_query or message

# ---------------------------------------------------------
# GUARDAR CONTEXTO
# ---------------------------------------------------------
async def guardar_contexto(user_id, conversation_id, user_message, ai_message, current_product_query: str | None = None):
    payload = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "user_message": user_message,
        "ai_message": ai_message,
    }
    async with httpx.AsyncClient(timeout=300.0) as client:
        await client.post(f"{WORKER_URL}/context/save", json=payload)

def limpiar_respuesta_mistral(texto: str) -> str:
    if not texto:
        return texto

    texto = re.sub(r"^(IA:\s*)+", "", texto.strip(), flags=re.IGNORECASE)
    texto = re.sub(r"INTENCION_DETECTADA\s*:\s*\w+", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s{2,}", " ", texto)
    texto = texto.strip()

    return texto

def extraer_intencion(respuesta: str) -> str:
    for linea in respuesta.splitlines():
        if "INTENCION_DETECTADA:" in linea:
            return linea.split(":", 1)[1].strip().upper()
    return "OTRA"

# ---------------------------------------------------------
# Selección de prompt por intención
# ---------------------------------------------------------
# ---------------------------------------------------------
# Selección de prompt por intención (refactorizado)
# ---------------------------------------------------------
def seleccionar_prompt_por_intencion(
    intencion: str,
    hay_vendedores: bool = False,
    hay_compradores: bool = False
) -> str:
    mapping = {
        "MENSAJERIA": "prompt_mensajeria.txt",
        "TRANSPORTE": "prompt_transporte.txt",
        "MULTI_INTENCION": "prompt_multi_intencion.txt",
        "NEGOCIOS": "prompt_negocios.txt",
        "CONTACTO": "prompt_contacto.txt",
    }

    # Si la intención está en el mapeo directo, devolvemos el prompt correspondiente
    if intencion in mapping:
        return mapping[intencion]

    # Caso especial: INFORMATIVA
    if intencion == "INFORMATIVA":
        if hay_vendedores:
            return "broker_prompt_vendedor.txt"
        if hay_compradores:
            return "broker_prompt_comprador.txt"
        return "prompt_general.txt"

    # Intenciones principales
    if intencion == "COMPRA":
        return "broker_prompt_vendedor.txt"   # IA actúa como vendedor
    if intencion == "VENTA":
        return "broker_prompt_comprador.txt"  # IA actúa como comprador

    # Fallback
    return "prompt_general.txt"

def cargar_prompt(nombre_archivo: str) -> str:
    base = "c:/HellenCommerce/app/prompts/" if platform.system() == "Windows" else "app/prompts/"
    return Path(base + nombre_archivo).read_text(encoding="utf-8")

# ---------------------------------------------------------
# ORQUESTADOR PRINCIPAL
# ---------------------------------------------------------
async def orchestrate(user_id: str, message: str, conversation_id: int | None = None, location: str | None = None) -> str:
    print("\n================= ORCHESTRATE =================", flush=True)
    print("👤 user_id:", user_id, flush=True)
    print("💬 message:", message, flush=True)
    print("🧵 conversation_id:", conversation_id, flush=True)
    print("📍 location:", location, flush=True)

    payload_worker = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "message": str(message),
        "location": location
    }

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(f"{WORKER_URL}/infer", json=payload_worker)
            # Aqui vienen los datos que se le pasa a Mistral para construir el Prompt
            datos = r.json().get("response", {})
            print(f"Datos del worker:\n{datos}\n", flush=True)
    except Exception as e:
        print(f"❌ [ORCH] ERROR worker:", e, flush=True)
        datos = {}

    rol = datos.get("rol", "comprador")
    datos_db = datos.get("datos_db", {})
    datos_rag = datos.get("datos_rag", "")
    contexto = datos.get("contexto", [])

    if datos_db.get("status") == "empty":
        respuesta = (
            "Lo siento, no tenemos información sobre algún vendedor disponible. "
            "¿Deseas que te notifique cuando disponga de un vendedor para la mercancía que solicitas?"
        )
        await guardar_contexto(user_id, conversation_id, message, respuesta)
        return respuesta

    listado_vendedores_validos = datos_db.get("content", [])
    listado_compradores_validos = datos_db.get("content", [])
    primer_vendedor = ""
    primer_comprador = ""

    if rol == "comprador" and listado_vendedores_validos: # [0]["tipo"] == "vendedor"
        vendedores_validos, vendedores_basura = filtrar_vendedores(listado_vendedores_validos)
        print(f">>> Vendedores Validos: {vendedores_validos}")

        vendedores = vendedores_validos if vendedores_validos else vendedores_basura
        # content_list = datos_db["content"]
        primer_vendedor = vendedores[0] if vendedores else {}
    
    if rol == "vendedor" and listado_compradores_validos:
        compradores_validos, compradores_basura = filtrar_compradores(listado_compradores_validos)
        print(f">>> Compradores Validos: {compradores_validos}")

        compradores = compradores_validos if compradores_validos else compradores_basura
        # content_list = datos_db["content"]
        primer_comprador = compradores[0] if compradores else {}

    prompt_base = "broker_prompt_vendedor.txt" if rol == "comprador" else "broker_prompt_comprador.txt"
    prompt_template = cargar_prompt(prompt_base)

    rag_limpio = datos_rag[-400:] if datos_rag else "Inicio de conversación limpia."
    
    if primer_vendedor:
        vars = {
            "rol": rol,
            "datos_db": datos_db,
            "datos_rag": rag_limpio,
            "contexto": contexto[-5:],
            "message": message,
            "mercancia": primer_vendedor.get("mercancia", ""),
            "mercancias": datos_db.get("mercancias", ""),
            "mercancia_previa": datos_db.get("mercancia_previa", ""),
            "nombre_vendedor": primer_vendedor.get("nombre", ""),
            "precio": primer_vendedor.get("precio", ""),
            "ubicacion": primer_vendedor.get("ubicacion", ""),
            "domicilio": primer_vendedor.get("domicilio", "")
        }
    
    else:
        vars = {
            "rol": rol,
            "datos_db": datos_db,
            "datos_rag": rag_limpio,
            "contexto": contexto[-5:],
            "message": message
        }

    full_prompt = PromptBuilder(prompt_template, vars).build()
    # print(f"FULL PROMPT >>>: {full_prompt}\n")

    # prompt_reducido = PromptReducer().reduce(full_prompt)
    # prompt_reducido = PromptCnfReducer().reduce(full_prompt)

    content = vars["datos_db"].get("content", [])
    message = vars.get("message", "")
    contexto_previo = vars.get("contexto", [])
    tipo = "vendedor" if rol == "comprador" else "comprador"
    reducer = PromptReducerUltra(content=content, contexto_previo=contexto_previo, message=message, role_broker=tipo)
    prompt_reducido = reducer.reduce(full_prompt)
    print(f">>> PROMPT REDUCIDO: {prompt_reducido}", flush=True)

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(
                f"{MISTRAL_URL}/infer",
                json={"prompt": prompt_reducido, "max_tokens": 128, "temperature": 0.3}
            )
            data = r.json()
            respuesta = data.get("response")
    except Exception:
        respuesta = "Lo siento, tuve un problema técnico."

    print(f"Respuesta Mistral (1ra pasada): {respuesta}\n")

    intencion = extraer_intencion(respuesta)
    print(f">>> INTENCIÓN DETECTADA: {intencion}\n")

    if intencion == "MENSAJERIA":
        datos_db = {}
        vars["datos_db"] = {}
        vars["mercancia"] = ""
        vars["mercancia_previa"] = ""
        vars["nombre_vendedor"] = ""
        vars["precio"] = ""
        vars["ubicacion"] = ""
        vars["domicilio"] = ""
        rol = "mensajeria"
        vars["rol"] = "mensajeria"

    elif intencion == "TRANSPORTE":
        datos_db = {}
        vars["datos_db"] = {}
        vars["mercancia"] = ""
        vars["mercancia_previa"] = ""
        vars["nombre_vendedor"] = ""
        vars["precio"] = ""
        vars["ubicacion"] = ""
        vars["domicilio"] = ""
        rol = "transporte"
        vars["rol"] = "transporte"

    elif intencion == "INFORMATIVA":
        datos_db = {}
        vars["datos_db"] = {}
        vars["mercancia"] = ""
        vars["mercancia_previa"] = ""
        vars["nombre_vendedor"] = ""
        vars["precio"] = ""
        vars["ubicacion"] = ""
        vars["domicilio"] = ""
        rol = "informativa"
        vars["rol"] = "informativa"

    elif intencion == "OTRA":
        datos_db = {}
        vars["datos_db"] = {}
        vars["mercancia"] = ""
        vars["mercancia_previa"] = ""
        vars["nombre_vendedor"] = ""
        vars["precio"] = ""
        vars["ubicacion"] = ""
        vars["domicilio"] = ""
        rol = "otra"
        vars["rol"] = "otra"
    
    elif intencion == "NEGOCIO":
        # No borrar datos_db: contiene negocios válidos
        vars["datos_db"] = datos_db

        # En NEGOCIO, la mercancía no aplica
        vars["mercancia"] = ""
        vars["mercancia_previa"] = ""

        # Campos específicos de vendedor NO aplican
        vars["nombre_vendedor"] = ""
        vars["precio"] = ""
        vars["ubicacion"] = ""
        vars["domicilio"] = ""

        # Rol especializado
        rol = "negocio"
        vars["rol"] = "negocio"
    
    elif intencion == "CONTACTO":
        # No borrar datos_db: contiene negocios válidos
        vars["datos_db"] = datos_db

        # En NEGOCIO, la mercancía no aplica
        vars["mercancia"] = primer_vendedor.get("mercancia", "")
        vars["mercancia_previa"] = datos_db.get("mercancia_previa", "")

        # Campos específicos de vendedor NO aplican
        vars["nombre_vendedor"] = primer_vendedor.get("nombre", "")
        vars["precio"] = primer_vendedor.get("precio", "")
        vars["ubicacion"] = primer_vendedor.get("ubicacion", "")
        vars["domicilio"] = ""

        # Rol especializado
        rol = "contacto"
        vars["rol"] = "contacto"

    # Detectar si hay vendedores o compradores en la DB
    hay_vendedores = bool(datos_db.get("content")) if rol == "comprador" else False
    hay_compradores = bool(datos_db.get("content")) if rol == "vendedor" else False

    # Seleccionar prompt especial según intención y presencia de vendedores/compradores
    prompt_especial = seleccionar_prompt_por_intencion(
        intencion,
        hay_vendedores=hay_vendedores,
        hay_compradores=hay_compradores
    )
    if prompt_especial != prompt_base:
        print(f">>> Cambiando a prompt especializado: {prompt_especial}\n")

        prompt_template_especial = cargar_prompt(prompt_especial)
        full_prompt = PromptBuilder(prompt_template_especial, vars).build()
        # print(f">>> PROMPT ESPECIALIZADO: {full_prompt}")

        # prompt_reducido = PromptReducer().reduce(full_prompt)
        # prompt_reducido = PromptCnfReducer().reduce(full_prompt)

        # content = vars["datos_db"].get("content", [])
        # contexto_previo = vars.get("contexto", [])
        # reducer = PromptReducerUltra(content=content, contexto_previo=contexto_previo)
        # prompt_reducido = reducer.reduce(full_prompt)
        print(f">>> PROMPT REDUCIDO: {full_prompt}", flush=True)

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                r = await client.post(
                    f"{MISTRAL_URL}/infer",
                    json={"prompt": full_prompt, "max_tokens": 128, "temperature": 0.3}
                )
                data = r.json()
                respuesta = data.get("response")
        except Exception:
            respuesta = "Lo siento, tuve un problema técnico."

        print(f"Respuesta Mistral (2da pasada): {respuesta}\n")

    respuesta = limpiar_respuesta_mistral(respuesta)
    await guardar_contexto(user_id, conversation_id, message, respuesta)

    return respuesta

# ---------------------------------------------------------
# WebSocket
# ---------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print("WS: aceptando conexión", flush=True)
    await websocket.accept()
    await websocket.send_json({"response": "Hola, soy Vainilla, tu IA que te acompaña en toda nuestra App."})

    async def heartbeat():
        while True:
            await asyncio.sleep(600)
            try:
                await websocket.send_json({"response": "💡 Conexión activa"})
            except WebSocketDisconnect:
                print("WS: heartbeat detectó desconexión", flush=True)
                break

    hb_task = asyncio.create_task(heartbeat())

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except Exception as e:
                print("❌ [FASTAPI] Formato de mensaje inválido:", e, flush=True)
                await websocket.send_json({"response": "Formato de mensaje inválido"})
                continue

            print("📥 [FASTAPI] RAW recibido:", repr(raw), flush=True)

            if not raw or not raw.strip():
                print("⚠️ [FASTAPI] Mensaje vacío o whitespace", flush=True)
                continue

            try:
                data = json.loads(raw)
                print("📦 [FASTAPI] JSON parseado:", data, flush=True)
            except Exception as e:
                print("❌ [FASTAPI] Error parseando JSON:", e, flush=True)
                await websocket.send_json({"response": "Formato de mensaje inválido"})
                continue

            user_id = data.get("user_id")
            conversation_id = data.get("conversation_id")
            message = data.get("message")
            location = data.get("ubicacion")
            context = data.get("contexto")
            print(f">>>>>>>>>>>> Contexto: {context}\n")

            if not user_id or not message:
                print("⚠️ [FASTAPI] Faltan campos obligatorios", flush=True)
                await websocket.send_json({"response": "Faltan campos obligatorios"})
                continue

            print("🚀 [FASTAPI] Llamando a orchestrate() con:", {
                "user_id": user_id,
                "message": message,
                "conversation_id": conversation_id
            }, flush=True)

            try:
                respuesta = await orchestrate(user_id, message, conversation_id, location)
                print("⬅️ [FASTAPI] orchestrate() devolvió:", respuesta, flush=True)
            except Exception as e:
                print(f"❌ [FASTAPI] ERROR en orchestrate(): {e}", flush=True)
                respuesta = message

            await websocket.send_json({"response": respuesta})

    except WebSocketDisconnect:
        print("WS: cliente desconectado", flush=True)

    finally:
        hb_task.cancel()

# ---------------------------------------------------------
# Endpoint HTTP /chat
# ---------------------------------------------------------
@app.post("/chat")
async def chat_api(data: UserMessage):
    respuesta = await orchestrate(data.user_id, data.message, data.conversation_id)
    return {"response": respuesta}

# ---------------------------------------------------------
# Endpoint notificaciones
# ---------------------------------------------------------
@app.post("/notificacion/leida")
async def marcar_notificacion_leida(data: NotificacionLeida):
    async with httpx.AsyncClient(timeout=300.0) as client:
        r = await client.post(
            f"{WORKER_URL}/notificacion/leida",
            json={"notif_id": data.notif_id, "user_id": data.user_id}
        )
    return r.json()

# ---------------------------------------------------------
# Endpoints de conversaciones y mensajes
# ---------------------------------------------------------
@app.get("/conversations/last5")
def get_last5(user_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM conversaciones
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 5
    """, (user_id,))
    return [dict(r) for r in cur.fetchall()]

@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mensajes WHERE conversation_id = ? ORDER BY created_at ASC", (conversation_id,))
    return {"messages": [dict(r) for r in cur.fetchall()]}

@app.post("/conversations")
def create_conversation(data: NewConversation):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM conversaciones WHERE user_id = ?", (data.user_id,))
    count = cur.fetchone()["c"]

    es_flag = 1 if count % 5 == 0 else 0
    if es_flag == 1:
        cur.execute("UPDATE conversaciones SET es_flag = 0 WHERE user_id = ? AND es_flag = 1", (data.user_id,))

    now = datetime.datetime.utcnow().isoformat()
    cur.execute("""
        INSERT INTO conversaciones (user_id, titulo, es_flag, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (data.user_id, None, es_flag, now, now))
    conn.commit()
    return {"id": cur.lastrowid, "user_id": data.user_id, "es_flag": es_flag, "created_at": now}

@app.post("/messages")
def save_message(data: NewMessage):
    conn = get_db()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()

    cur.execute("""
        INSERT INTO mensajes (conversation_id, user_id, rol, contenido, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (data.conversation_id, data.user_id, data.rol, data.contenido, now))

    conn.commit()
    return {
        "status": "ok",
        "conversation_id": data.conversation_id,
        "user_id": data.user_id,
        "rol": data.rol,
        "contenido": data.contenido,
        "created_at": now
    }

# ---------------------------------------------------------
# Productos por negocio (Tienda)
# ---------------------------------------------------------
@app.get("/business/{business_id}/products")
def get_products(business_id: str):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM products WHERE business_id = ?", (business_id,))
    rows = cur.fetchall()

    return [dict(r) for r in rows]

@app.post("/business/{business_id}/products")
def create_product(business_id: str, data: ProductCreate):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO products (user_id, business_id, name, price, description, image)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        data.user_id,
        business_id,
        data.name,
        data.price,
        data.description,
        data.image
    ))

    conn.commit()
    return {"status": "ok", "id": cur.lastrowid}

@app.post("/business/by_bounds")
def businesses_by_bounds(payload: dict = Body(...)):
    bounds = payload["bounds"]

    sw = bounds["_southWest"]
    ne = bounds["_northEast"]

    min_lat = sw["lat"]
    min_lng = sw["lng"]
    max_lat = ne["lat"]
    max_lng = ne["lng"]

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM businesses
        WHERE lat BETWEEN ? AND ?
        AND lng BETWEEN ? AND ?
    """, (min_lat, max_lat, min_lng, max_lng))

    rows = cur.fetchall()

    return {"businesses": [dict(r) for r in rows]}

@app.post("/api/set_location")
def set_location(data: dict, db = Depends(get_db)):
    lat = data.get("lat")
    lon = data.get("lon")

    if lat is None or lon is None:
        return {"status": "error", "msg": "lat/lon faltan"}

    user_id = "default_user"  # por ahora

    cur = db.cursor()
    cur.execute("""
        UPDATE usuarios
        SET lat = ?, lon = ?, timestamp = CURRENT_TIMESTAMP
        WHERE user_id = ?
    """, (lat, lon, user_id))

    db.commit()

    return {"status": "ok"}

@app.post("/api/auth/google")
async def auth_google(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    id_token = authorization.replace("Bearer ", "")

    try:
        decoded = firebase_auth.verify_id_token(id_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = {
        "uid": decoded["uid"],
        "email": decoded.get("email"),
        "name": decoded.get("name"),
        "picture": decoded.get("picture")
    }

    return {
        "user": user,
        "token": "TOKEN_GENERADO_POR_TU_BACKEND"
    }

# @app.post("/admin/clean-db")
# def clean_db():
#     clean_database()
#     return {"status": "ok", "message": "DB limpiada correctamente"}

# ---------------------------------------------------------
# Health check
# ---------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

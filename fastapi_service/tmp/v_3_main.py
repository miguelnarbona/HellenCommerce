from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Depends, HTTPException, Header
from contextlib import asynccontextmanager
from firebase_admin import auth as firebase_auth
import firebase_admin
from firebase_admin import credentials
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, Depends
import psutil
import socket
import httpx
import os
import re
import platform
import asyncio
import json
import sqlite3
import datetime
from dataclasses import dataclass
from typing import Any, Dict

from app.core.pipeline.PromptBuilder import PromptBuilder
from app.core.pipeline.PromptReducer import PromptReducer
from app.core.pipeline.PromptCnfReducer import PromptCnfReducer
from app.core.pipeline.PromptReducerUltra import PromptReducerUltra

# cred = credentials.Certificate(
#     r"C:\HellenCommerce\fastapi_service\firebase-admin.json"
# )
# firebase_admin.initialize_app(cred)

# ---------------------------------------------------------
# Health Sockets on Startup
# Lifespan context manager
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    task = asyncio.create_task(socket_maintenance())
    print(f"🚀 Servicio de mantenimiento de sockets iniciado en {platform.system()}")

    yield  # aquí corre la aplicación

    # Shutdown
    task.cancel()
    print("🛑 Backend apagándose, servicio de mantenimiento detenido")

app = FastAPI(
    title="IA Broker Multicanal",
    description="API pública que orquesta worker_service + mistral_service + HF.",
    version="2.1.0",
    lifespan=lifespan
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

# ----------------------------------------------------------
# Terminos y Definiciones
#-----------------------------------------------------------
LOWER_LIMIT = 30000
UPPER_LIMIT = 50000
CHECK_INTERVAL = 5 # en segundos, tiempo cada vez que despierta y corre el mantenimiento de socket
CRITICAL_STATES = {"CLOSE_WAIT", "TIME_WAIT", "FIN_WAIT1", "FIN_WAIT2"}
BACKEND_PIDS = {os.getpid()}  # PID del backend

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
BASE_PRT = f"c:/HellenCommerce/app/prompts" if system == "Windows" else "app/prompts"
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
# Funciones auxiliares para orchestrate
# ---------------------------------------------------------
@dataclass
class WorkerData:
    rol: str
    datos_db: Dict[str, Any]
    datos_rag: str
    contexto: list

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
# Mantenimiento de Sockets
# ---------------------------------------------------------
async def socket_maintenance():
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            conns = psutil.net_connections(kind="tcp")
            total = len(conns)
            # print(f"🔎 Total sockets: {total}")

            # Si supera el límite inferior, cerrar sockets externos de baja prioridad
            if total > LOWER_LIMIT:
                for conn in conns:
                    if conn.pid in BACKEND_PIDS:
                        continue  # no tocar sockets del backend
                    if conn.status in CRITICAL_STATES and conn.fd != -1:
                        try:
                            s = socket.fromfd(conn.fd, socket.AF_INET, socket.SOCK_STREAM)
                            s.close()
                            print(f"🔒 Cerrado socket externo {conn.laddr} -> {conn.raddr} [{conn.status}]")
                        except Exception as e:
                            print(f"❌ Error cerrando socket {conn}: {e}")

            # Si supera el límite superior, aplicar medidas más drásticas
            if total > UPPER_LIMIT:
                print("⚠️ Umbral superior alcanzado, aplicar medidas drásticas (reinicio de servicios, etc.)")

        except Exception as e:
            print(f"❌ Error en mantenimiento de sockets: {e}")

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

async def fetch_worker_data(user_id: str, message: str, conversation_id: int | None, location: str | None) -> WorkerData:
    payload = {
        "user_id": user_id, 
        "conversation_id": conversation_id, 
        "message": str(message), 
        "location": location
        }
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(f"{WORKER_URL}/infer", json=payload)
            datos = r.json().get("response", {})
            print(f"Datos del worker:\n{datos}\n", flush=True)
    except Exception as e:
        print(f"❌ [ORCH] ERROR worker:", e, flush=True)
        datos = {}
    return WorkerData(
        rol=datos.get("rol", "comprador"),
        datos_db=datos.get("datos_db", {}),
        datos_rag=datos.get("datos_rag", ""),
        contexto=datos.get("contexto", [])
    )

def build_prompt_vars(rol: str, datos_db: Dict[str, Any], datos_rag: str, contexto: list, message: str) -> Dict[str, Any]:
    rag_limpio = datos_rag[-400:] if datos_rag else "Inicio de conversación limpia."
    return {"rol": rol, "datos_db": datos_db, "datos_rag": rag_limpio, "contexto": contexto[-5:], "message": message}

def limpiar_campos(vars: Dict[str, Any]) -> None:
    for campo in ["mercancia", "mercancia_previa", "nombre_vendedor", "precio", "ubicacion", "domicilio"]:
        vars[campo] = ""

def clean_vars_for_intention(vars: Dict[str, Any], intencion: str, datos_db: Dict[str, Any], primer_vendedor: dict) -> Dict[str, Any]:
    rules = {
        "MENSAJERIA": {"rol": "mensajeria", "clear_fields": True},
        "TRANSPORTE": {"rol": "transporte", "clear_fields": True},
        "INFORMATIVA": {"rol": "informativa", "clear_fields": True},
        "OTRA": {"rol": "otra", "clear_fields": True},
        "NEGOCIO": {"rol": "negocio", "clear_fields": False},
        "CONTACTO": {"rol": "contacto", "clear_fields": False},
    }
    rule = rules.get(intencion)
    if not rule:
        return vars
    vars["rol"] = rule["rol"]
    if rule["clear_fields"]:
        limpiar_campos(vars)
        vars["datos_db"] = {}
    else:
        vars["datos_db"] = datos_db
        if intencion == "CONTACTO":
            vars["mercancia"] = primer_vendedor.get("mercancia", "")
            vars["mercancia_previa"] = datos_db.get("mercancia_previa", "")
            vars["nombre_vendedor"] = primer_vendedor.get("nombre", "")
            vars["precio"] = primer_vendedor.get("precio", "")
            vars["ubicacion"] = primer_vendedor.get("ubicacion", "")
            vars["domicilio"] = ""
    return vars

async def run_mistral_with_prompt(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(f"{MISTRAL_URL}/infer", json={"prompt": prompt, "max_tokens": 128, "temperature": 0.3})
            return r.json().get("response", "Lo siento, tuve un problema técnico.")
    except Exception:
        return "Lo siento, tuve un problema técnico."

# ---------------------------------------------------------
# Orchestrate refactorizado
# rol: es el role de usuario
# role: es el role de la IA, correspondiente al que esta en la base de datos
# ---------------------------------------------------------
async def orchestrate(user_id: str, message: str, conversation_id: int | None = None, location: str | None = None) -> str:
    print("\n================= ORCHESTRATE =================", flush=True)
    datos = await fetch_worker_data(user_id, message, conversation_id, location)

    vars = build_prompt_vars(datos.rol, datos.datos_db, datos.datos_rag, datos.contexto, message)
    # prompt_base es el role de la IA, el comportamiento que asumira la IA
    prompt_base = "broker_prompt_vendedor.txt" if datos.rol == "comprador" else "broker_prompt_comprador.txt"
    full_prompt = PromptBuilder(Path(f"{BASE_PRT}/{prompt_base}").read_text(encoding="utf-8"), vars).build()
    roleIA = "vendedor" if datos.rol == "comprador" else "comprador"
    contenido = datos.datos_db.get("content", [])
    contextual = datos.contexto[-3:]
    
    print(f">>>>>>> PROMPT: {full_prompt}\n", flush=True)
    print(f"Broker Role (IA): {roleIA}\n", flush=True)
    print(f">>> Content: {contenido}\n", flush=True)
    print(f">>> Contexto: {contextual}\n", flush=True)
    print(f">>> Message: {message}\n", flush=True)

    reducer = PromptReducerUltra(
        content=datos.datos_db.get("content", []),
        contexto_previo=datos.contexto[-3:],
        message=message,
        role_broker="vendedor" if datos.rol == "comprador" else "comprador"
    )
    prompt_reducido = reducer.reduce(full_prompt)
    print(f">>>>>>> PROMPT REDUCIDO: {prompt_reducido}\n", flush=True)
    
    respuesta = await run_mistral_with_prompt(prompt_reducido)
    print(f">>>>>>> Respuesta : {respuesta}\n", flush=True)

    intencion = re.search(r"INTENCION_DETECTADA:\s*(\w+)", respuesta or "")
    intencion = intencion.group(1).upper() if intencion else "OTRA"
    vars = clean_vars_for_intention(vars, intencion, datos.datos_db, {})

    print(f"INTENCION DETECTADA: {intencion}\n", flush=True)

    prompt_especial = "prompt_general.txt"
    if intencion == "VENTA":
        prompt_especial = "broker_prompt_comprador.txt"
    elif intencion == "COMPRA":
        prompt_especial = "broker_prompt_vendedor.txt"

    if prompt_especial != prompt_base:
        print("SEGUNDA LLAMADA A MISTRAL", flush=True)
        full_prompt = PromptBuilder(Path(f"{BASE_PRT}/{prompt_especial}").read_text(encoding="utf-8"), vars).build()
        respuesta = await run_mistral_with_prompt(full_prompt)

    respuesta = re.sub(r"^(IA:\s*)+", "", respuesta.strip(), flags=re.IGNORECASE)
    print(f">>>> Respuesta SEGUNDA LLAMADA: {respuesta}\n", flush=True)

    await guardar_contexto(user_id, conversation_id, message, respuesta)
    return respuesta

# ---------------------------------------------------------
# WebSocket
# ---------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"response": "Hola, soy Vainilla, tu IA que te acompaña en toda nuestra App."})
    async def heartbeat():
        while True:
            await asyncio.sleep(600)
            try:
                await websocket.send_json({"response": "💡 Conexión activa"})
            except WebSocketDisconnect:
                break
    hb_task = asyncio.create_task(heartbeat())
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            user_id = data.get("user_id")
            conversation_id = data.get("conversation_id")
            message = data.get("message")
            location = data.get("ubicacion")

            if not user_id or not message:
                await websocket.send_json({"response": "Faltan campos obligatorios"})
                continue

            try:
                respuesta = await orchestrate(user_id, message, conversation_id, location)
            except Exception as e:
                print(f"❌ [FASTAPI] ERROR en orchestrate(): {e}", flush=True)
                respuesta = "Lo siento, ocurrió un error interno."

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
    """, (data.user_id, business_id, data.name, data.price, data.description, data.image))
    conn.commit()
    return {"status": "ok", "id": cur.lastrowid}

@app.post("/business/by_bounds")
def businesses_by_bounds(payload: dict = Body(...)):
    bounds = payload["bounds"]
    sw = bounds["_southWest"]
    ne = bounds["_northEast"]
    min_lat, min_lng = sw["lat"], sw["lng"]
    max_lat, max_lng = ne["lat"], ne["lng"]

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
    user_id = "default_user"  # placeholder
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
    return {"user": user, "token": "TOKEN_GENERADO_POR_TU_BACKEND"}

# ---------------------------------------------------------
# Health check
# ---------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}
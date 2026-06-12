import asyncio
import sys

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Depends, HTTPException, Header
from contextlib import asynccontextmanager
from llama_cpp import Llama
from firebase_admin import auth as firebase_auth
import firebase_admin
from firebase_admin import credentials
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from pydantic import BaseModel
import psutil
import socket
import httpx
import os
import re
import platform
import json
import sqlite3
import datetime
from dataclasses import dataclass
from typing import Any, Dict
import unicodedata
import re
from pathlib import Path

from app.core.pipeline.PromptBuilder import PromptBuilder
from app.core.pipeline.PromptReducerUltra import PromptReducerUltra
from app.context.ContextManager import ContextManager
from app.adapters.db.SQLiteAdapter import SQLiteAdapter
from fastapi_service.library.orchestrate import Orchestrator

# COPILOT-add:
# Inicializar ContextManager global para gestionar memoria conversacional
# Esto asegura que el contexto se mantenga a lo largo de múltiples interacciones
context_manager = None
orchestrator_instance = None

# ---------------------------------------------------------
# Lifespan context manager
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global context_manager
    
    # COPILOT-add:
    # Inicializar el ContextManager global al arranque de la aplicación
    # Esto asegura que la memoria conversacional esté disponible para todas las solicitudes
    try:
        # COPILOT-Change:
        # El ContextManager necesita un adaptador con _get_conn(), no una conexión sqlite3 directa.
        # Usar SQLiteAdapter garantiza compatibilidad con las operaciones de carga/guardado.
        sqlite_adapter = SQLiteAdapter()
        context_manager = ContextManager(
            db=sqlite_adapter,
            max_lines=5,
            rag=None,        # Se puede configurar después si ChromaDB está disponible
            embedder=None,   # Se puede configurar después si está disponible
            query_adapter=None
        )
        print("✅ ContextManager inicializado correctamente", flush=True)
    except Exception as e:
        print(f"⚠️ Error inicializando ContextManager: {e}", flush=True)
        context_manager = None
    
    global orchestrator_instance
    orchestrator_instance = Orchestrator(
        context_manager=context_manager,
        cola_modelo=cola_modelo,
        get_db_func=get_db,
        worker_url=WORKER_URL,
        base_prt=BASE_PRT
    )
    
    task_socket = asyncio.create_task(socket_maintenance())
    print(f"🚀 Servicio de mantenimiento de sockets iniciado en {platform.system()}")
    
    # task_startup = asyncio.create_task(start_up_event())
    # print(f"🚀 Cragando Modelos desde HF ... on {platform.system()}")

    # Tarea 3: iniciar el worker del modelo
    task_worker = asyncio.create_task(worker_modelo())
    print("⚙️ Worker del modelo iniciado y esperando tareas...")

    yield

    task_socket.cancel()
    # task_startup.cancel()
    task_worker.cancel()
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

# ---------------------------------------------------------
# Configuración
# ---------------------------------------------------------
LOWER_LIMIT = 30000
UPPER_LIMIT = 50000
CHECK_INTERVAL = 5
CRITICAL_STATES = {
    "CLOSE_WAIT", 
    "TIME_WAIT", 
    "FIN_WAIT1", 
    "FIN_WAIT2"
    }
BACKEND_PIDS = {os.getpid()}

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
BASE_RES = f"c:/HellenCommerce/app/resources" if system == "Windows" else "app/resources"
BASE_PRT = f"c:/HellenCommerce/app/prompts" if system == "Windows" else "app/prompts"

# ---------------------------------------------------------
# Modelos
# ---------------------------------------------------------
class NewConversation(BaseModel):
    user_id: str

class NotificacionLeida(BaseModel):
    notif_id: int
    user_id: str
    
class UserMessage(BaseModel):
    conversation_id: int | None = None
    message: str

class NewMessage(BaseModel):
    rol: str
    contenido: str

class ProductCreate(BaseModel):
    name: str
    price: float
    description: str | None = None
    image: str | None = None

class CommStatusUpdate(BaseModel):
    status: str
    social_links: dict | None = None


# ---------------------------------------------------------
# DB Helpers
# ---------------------------------------------------------
def get_db():
    conn = sqlite3.connect(os.getenv("SQLITE_PATH"), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------------------------------------
# Creacion de Cola para run_mistral
# ---------------------------------------------------------
cola_modelo = asyncio.Queue()

async def worker_modelo():
    while True:
        prompt, future = await cola_modelo.get()
        try:
            respuesta = await run_mistral_with_prompt(prompt)
            future.set_result(respuesta)
        except Exception:
            future.set_result("Lo siento, tuve un problema técnico.")
        finally:
            cola_modelo.task_done()

# ---------------------------------------------------------
# Socket maintenance
# ---------------------------------------------------------
async def socket_maintenance():
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            conns = psutil.net_connections(kind="tcp")
            total = len(conns)
            if total > LOWER_LIMIT:
                for conn in conns:
                    if conn.pid in BACKEND_PIDS:
                        continue
                    if conn.status in CRITICAL_STATES and conn.fd != -1:
                        try:
                            s = socket.fromfd(conn.fd, socket.AF_INET, socket.SOCK_STREAM)
                            s.close()
                        except Exception:
                            pass
            if total > UPPER_LIMIT:
                print("⚠️ Umbral superior alcanzado")
        except Exception as e:
            print(f"❌ Error en mantenimiento de sockets: {e}")

# ---------------------------------------------------------
# Helpers & Utilities
# ---------------------------------------------------------

async def run_mistral_with_prompt(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=1200) as client:
            r = await client.post(f"{MISTRAL_URL}/infer", json={"prompt": prompt, "max_tokens": 384, "temperature": 0.3})
            return r.json().get("response", "Lo siento, tuve un problema técnico.")
    except Exception:
        return "Lo siento, tuve un problema técnico."

# ---------------------------------------------------------
# Orchestrate
# ---------------------------------------------------------

# ---------------------------------------------------------
# WebSocket
# ---------------------------------------------------------
modelo_lock = asyncio.Lock()
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    async with modelo_lock:
        await websocket.accept()

        async def heartbeat():
            while True:
                await asyncio.sleep(1200)
                try:
                    await websocket.send_json({"response": "💡 Conexión activa"})
                except WebSocketDisconnect:
                    print(f"WS: heartbeat detectó desconexión para {user_id}", flush=True)
                    break

        hb_task = asyncio.create_task(heartbeat())

        try:
            while True:
                try:
                    raw = await websocket.receive_text()
                except WebSocketDisconnect:
                    print(f"WS: cliente {user_id} desconectado", flush=True)
                    break  # salir del bucle sin lanzar excepción
                
                # Aqui tomo la conversacion entrada 
                data = json.loads(raw)
                conversation_id = data.get("conversation_id")
                message = data.get("message")
                location = data.get("ubicacion")

                if not message:
                    await websocket.send_json({"response": "Faltan campos obligatorios"})
                    continue

                try:
                    # Pasar la informacion al modelo mediante el orquestador
                    # ... el se ocupa de todo ...
                    result = await orchestrator_instance.orchestrate(user_id, message, conversation_id, location)
                    if isinstance(result, dict):
                        print (f">>>>>>>>> Instancia websocket.send_json(result): {result} <<<<<<<<<<<<\n", flush=True)
                        await websocket.send_json({"response": result})
                    else:
                        print (f">>>>>>>>> Instancia websocket.send_json(response: result): {result} <<<<<<<<<<<<\n", flush=True)
                        await websocket.send_json({"response": result})

                except Exception as e:
                    print(f"❌ [FASTAPI] ERROR en orchestrate(): {e}", flush=True)
                    await websocket.send_json({"response": "Lo siento, ocurrió un error interno."})

        finally:
            hb_task.cancel()
            try:
                await websocket.close()
            except Exception:
                pass

# ---------------------------------------------------------
# Endpoint HTTP /chat
# ---------------------------------------------------------
@app.post("/user/{user_id}/chat")
async def chat_api(user_id: str, data: UserMessage):
    result = await orchestrator_instance.orchestrate(user_id, data.message, data.conversation_id)
    if isinstance(result, dict):
        return result
    return {"response": result}

# ---------------------------------------------------------
# Endpoint notificaciones
# ---------------------------------------------------------
@app.post("/user/{user_id}/notificacion/{notif_id}/leida")
async def marcar_notificacion_leida(user_id: str, notif_id: int):
    async with httpx.AsyncClient(timeout=1200.0) as client:
        r = await client.post(f"{WORKER_URL}/user/{user_id}/notificacion/{notif_id}/leida")
    return r.json()

# ---------------------------------------------------------
# Endpoints de conversaciones y mensajes
# ---------------------------------------------------------
@app.get("/user/{user_id}/conversations/last5")
def get_last5(user_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM conversaciones WHERE user_id = ? ORDER BY created_at DESC LIMIT 5", (user_id,))
    return [dict(r) for r in cur.fetchall()]

@app.get("/user/{user_id}/conversations/{conversation_id}")
def get_conversation(user_id: str, conversation_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mensajes WHERE conversation_id = ? AND user_id = ? ORDER BY created_at ASC", (conversation_id, user_id))
    return {"messages": [dict(r) for r in cur.fetchall()]}

@app.post("/user/{user_id}/conversations")
def create_conversation(user_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM conversaciones WHERE user_id = ?", (user_id,))
    count = cur.fetchone()["c"]
    es_flag = 1 if count % 5 == 0 else 0
    if es_flag == 1:
        cur.execute("UPDATE conversaciones SET es_flag = 0 WHERE user_id = ? AND es_flag = 1", (user_id,))
    now = datetime.datetime.utcnow().isoformat()
    cur.execute("INSERT INTO conversaciones (user_id, titulo, es_flag, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, None, es_flag, now, now))
    conn.commit()
    return {"id": cur.lastrowid, "user_id": user_id, "es_flag": es_flag, "created_at": now}

@app.post("/user/{user_id}/conversations/{conversation_id}/messages")
def save_message(user_id: str, conversation_id: int, data: NewMessage):
    conn = get_db()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    cur.execute("INSERT INTO mensajes (conversation_id, user_id, rol, contenido, created_at) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, user_id, data.rol, data.contenido, now))
    conn.commit()
    return {"status": "ok", "conversation_id": conversation_id, "user_id": user_id,
            "rol": data.rol, "contenido": data.contenido, "created_at": now}

# ---------------------------------------------------------
# Productos por negocio
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
        INSERT INTO products (business_id, name, price, description, image)
        VALUES (?, ?, ?, ?, ?)
    """, (business_id, data.name, data.price, data.description, data.image))
    conn.commit()
    
    # 🔥 NUEVO: Verificar alertas de usuarios
    try:
        if context_manager and context_manager.db:
            # Obtenemos el nombre del negocio para el mensaje
            cur.execute("SELECT name FROM businesses WHERE id = ?", (business_id,))
            biz = cur.fetchone()
            biz_name = biz["name"] if biz else "un negocio"
            context_manager.db.verificar_alertas("vendedor", data.name, biz_name)
    except Exception as e:
        print(f"⚠️ Error al verificar alertas tras producto: {e}", flush=True)

    return {"status": "ok", "id": cur.lastrowid}

@app.post("/user/{user_id}/business/by_bounds")
def businesses_by_bounds(user_id: str, payload: dict = Body(...)):
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

@app.get("/user/{user_id}/business/nearby")
def get_nearby_businesses(user_id: str, lat: float, lng: float, radius_km: float = 1.0):
    # Simplificación: 1 grado lat ~ 111km, 1 grado lng ~ 111km * cos(lat)
    # Para 1km: delta_lat = 1/111 ~ 0.009
    delta = radius_km / 111.0
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM businesses
        WHERE lat BETWEEN ? AND ?
        AND lng BETWEEN ? AND ?
    """, (lat - delta, lat + delta, lng - delta, lng + delta))
    rows = cur.fetchall()
    return {"businesses": [dict(r) for r in rows]}

# ---------------------------------------------------------
# Ubicación de usuario
# ---------------------------------------------------------
@app.post("/user/{user_id}/location")
def set_location(user_id: str, data: dict, db = Depends(get_db)):
    lat = data.get("lat")
    lon = data.get("lon")
    if lat is None or lon is None:
        return {"status": "error", "msg": "lat/lon faltan"}
    cur = db.cursor()
    cur.execute("""
        UPDATE usuarios
        SET lat = ?, lon = ?, timestamp = CURRENT_TIMESTAMP
        WHERE user_id = ?
    """, (lat, lon, user_id))
    db.commit()
    return {"status": "ok"}

# ---------------------------------------------------------
# 🔥 COMUNICACIÓN (comm_services)
# ---------------------------------------------------------
@app.post("/user/{user_id}/comm/status")
def update_comm_status(user_id: str, data: CommStatusUpdate):
    try:
        if context_manager and context_manager.db:
            context_manager.db.update_comm_status(user_id, data.status, data.social_links)
            return {"status": "ok"}
        return {"status": "error", "msg": "DB adapter not available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user/{user_id}/comm/info")
def get_comm_info(user_id: str):
    try:
        if context_manager and context_manager.db:
            info = context_manager.db.get_user_comm_info(user_id)
            if not info:
                raise HTTPException(status_code=404, detail="User communication info not found")
            return info
        return {"status": "error", "msg": "DB adapter not available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# Autenticación con Google
# ---------------------------------------------------------
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

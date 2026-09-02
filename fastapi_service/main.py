"""
HellenCommerce 2.0.1 - FastAPI Ingress Service

Punto de entrada único para todas las peticiones de la AppWeb.
Utiliza el Orchestrator como librería interna (NO como microservicio externo).

Arquitectura:
- WebSocket endpoint para conexiones persistentes con clientes
- HTTP endpoints para operaciones REST
- Importa Orchestrator directamente desde app.core.orchestrator
- Todas las comunicaciones internas son asíncronas
"""

import asyncio
import sys
import platform
import json
import logging
import sqlite3
import datetime
import os
import httpx
import psutil
import socket
from app.utils.paths import hc_path, data_path

# Add root directory to path to enable imports from 'app' package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Depends, HTTPException, Header

from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers
from fastapi.middleware.trustedhost import TrustedHostMiddleware 
# 🚀 NUEVA IMPORTACIÓN PARA EL MIDDLEWARE DE WEBSOCKETS EN STARLETTE:
from starlette.types import ASGIApp, Scope, Receive, Send
from contextlib import asynccontextmanager

from pydantic import BaseModel
from firebase_admin import auth as firebase_auth
import firebase_admin

# Importar librerías compartidas desde /app/
from app.context.ContextManager import ContextManager
from app.adapters.db.SQLiteAdapter import SQLiteAdapter

# Importar Orquestador como librería interna (NO microservicio)
from app.core.orchestrator import Orchestrator

# ============================================================
# CONFIGURACIÓN
# ============================================================
LOWER_LIMIT = 30000
UPPER_LIMIT = 50000
CHECK_INTERVAL = 5
CRITICAL_STATES = {"CLOSE_WAIT", "TIME_WAIT", "FIN_WAIT1", "FIN_WAIT2"}
BACKEND_PIDS = {os.getpid()}

BASE_RES = hc_path("app/resources")
BASE_PRT = hc_path("app/prompts")
HF_API_KEY = os.getenv("HF_API_KEY", "")
SQLITE_PATH = data_path("sqlite_store/hellencommerce.db")

# Variables globales
context_manager = None
orchestrator_instance = None

# ============================================================
# MODELOS DE DATOS
# ============================================================
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

# ============================================================
# LIFESPAN - Inicialización de la aplicación
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global context_manager, orchestrator_instance    
    
    try:
        # Inicializar SQLiteAdapter
        sqlite_adapter = SQLiteAdapter()
        
        # Aplicar PRAGMAs de optimización
        try:
            conn = sqlite_adapter._get_conn()
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.close()
        except Exception as e:
            print(f"⚠️ Error aplicando PRAGMAs: {e}", flush=True)
        
        # Inicializar ContextManager
        context_manager = ContextManager(
            db=sqlite_adapter,
            max_lines=5,
            rag=None,
            embedder=None,
            query_adapter=None
        )
        print("✅ ContextManager inicializado correctamente", flush=True)
    except Exception as e:
        print(f"⚠️ Error inicializando ContextManager: {e}", flush=True)
        context_manager = None
    
    try:
        # Inicializar Orchestrator como librería interna
        orchestrator_instance = Orchestrator(
            context_manager=context_manager,
            get_db_func=get_db,
            base_prompts_path=BASE_PRT,
            base_resources_path=BASE_RES
        )
        print("✅ Orchestrator inicializado como librería interna", flush=True)
    except Exception as e:
        print(f"⚠️ Error inicializando Orchestrator: {e}", flush=True)
        orchestrator_instance = None
    
    # Iniciar tarea de mantenimiento de sockets
    task_socket = asyncio.create_task(socket_maintenance())
    print(f"🚀 Servicio de mantenimiento de sockets iniciado en {platform.system()}", flush=True)
    
    yield
    
    # Limpieza al apagar
    task_socket.cancel()
    print("🛑 FastAPI Ingress apagándose", flush=True)

app = FastAPI(
    title="HellenCommerce 2.0.1 - IA Broker Multicanal",
    description="API pública y WebSocket endpoint. Utiliza Orchestrator como librería interna.",
    version="2.0.1",
    lifespan=lifespan
)

# 🚀 1. MIDDLEWARE PERSONALIZADO: Reescribe el Host para WebSockets puros antes de CORS
@app.middleware("http")
async def fix_websocket_cloudflare_host(request, call_next):
    if request.headers.get("upgrade") == "websocket" or request.scope.get("type") == "websocket":
        origin = request.headers.get("origin")
        if origin:
            host_from_origin = origin.split("//")[-1]
            headers = dict(request.scope["headers"])
            headers[b"host"] = host_from_origin.encode("latin-1")
            request.scope["headers"] = list(headers.items())
            
    return await call_next(request)

# Middleware complementario para inyección a nivel de protocolo ASGI (Evita fugas de validación de Starlette)
class CloudflareWebSocketFixMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "websocket":
            headers = dict(scope.get("headers", []))
            # Buscar cabecera de origen codificada en bytes de forma segura
            origin = headers.get(b"origin", b"").decode("latin-1")
            if origin:
                host_from_origin = origin.split("//")[-1]
                headers[b"host"] = host_from_origin.encode("latin-1")
                scope["headers"] = list(headers.items())
        await self.app(scope, receive, send)

app.add_middleware(CloudflareWebSocketFixMiddleware)

# 🚀 2. MIDDLEWARES ESTÁNDAR
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"https://.*\.trycloudflare\.com",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# MANTENIMIENTO DE SOCKETS
# ============================================================
async def socket_maintenance():
    """Mantiene limpia la tabla de conexiones del sistema."""
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
                print("⚠️ Umbral superior de conexiones alcanzado", flush=True)
        except Exception as e:
            print(f"❌ Error en mantenimiento de sockets: {e}", flush=True)

# ============================================================
# DB HELPERS
# ============================================================
def get_db():
    """Obtiene conexión a SQLite."""
    conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================
# WEBSOCKET - Endpoint principal
# ============================================================
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint para conexiones persistentes con la AppWeb.
    Reenvía todas las peticiones al Orchestrator (librería interna).
    """
    await websocket.accept()

    async def heartbeat():
        """Envía heartbeat periódico para mantener la conexión viva."""
        while True:
            await asyncio.sleep(1200)
            try:
                await websocket.send_json({"response": "💡 Conexión activa"})
            except WebSocketDisconnect:
                break

    hb_task = asyncio.create_task(heartbeat())

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                print(f"📡 Cliente {user_id} desconectado", flush=True)
                break
            
            try:
                data = json.loads(raw)
                conversation_id = data.get("conversation_id")
                message = data.get("message")
                location = data.get("ubicacion")
                
                if not message:
                    await websocket.send_json({"response": "Mensaje vacío"})
                    continue
                
                # Verificar que el orchestrator esté disponible
                if not orchestrator_instance:
                    await websocket.send_json({
                        "response": "El sistema no está disponible en este momento. Por favor intenta de nuevo."
                    })
                    continue
                
                # Pasar la petición al Orchestrator (librería interna)
                result = await orchestrator_instance.orchestrate(
                    user_id=user_id,
                    message=message,
                    conversation_id=conversation_id,
                    location=location
                )
                
                # Enviar respuesta al cliente
                if isinstance(result, dict):
                    await websocket.send_json(result)
                else:
                    await websocket.send_json({"response": result})
                    
            except json.JSONDecodeError:
                await websocket.send_json({"response": "Formato de mensaje inválido"})
            except Exception as e:
                print(f"❌ Error procesando mensaje: {e}", flush=True)
                await websocket.send_json({"response": "Error interno procesando tu mensaje"})
                
    finally:
        hb_task.cancel()
        try:
            await websocket.close()
        except:
            pass

# ============================================================
# HTTP ENDPOINTS
# ============================================================
@app.post("/user/{user_id}/chat")
async def chat_api(user_id: str, data: UserMessage):
    """Endpoint HTTP alternativo para chat (cuando WebSocket no está disponible)."""
    if not orchestrator_instance:
        raise HTTPException(status_code=503, detail="Orchestrator no disponible")
    
    result = await orchestrator_instance.orchestrate(
        user_id=user_id,
        message=data.message,
        conversation_id=data.conversation_id
    )
    
    if isinstance(result, dict):
        return result
    return {"response": result}

@app.post("/user/{user_id}/notificacion/{notif_id}/leida")
async def marcar_notificacion_leida(user_id: str, notif_id: int):
    """Marca una notificación como leída."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        worker_url = os.getenv("WORKER_SERVICE_URL", "http://worker_service:9000")
        r = await client.post(f"{worker_url}/user/{user_id}/notificacion/{notif_id}/leida")
    return r.json()

@app.get("/user/{user_id}/conversations/last5")
def get_last5(user_id: str):
    """Obtiene las últimas 5 conversaciones del usuario."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM conversaciones WHERE user_id = ? ORDER BY created_at DESC LIMIT 5", (user_id,))
    results = [dict(r) for r in cur.fetchall()]
    conn.close()
    return results

@app.get("/user/{user_id}/conversations/{conversation_id}")
def get_conversation(user_id: str, conversation_id: int):
    """Obtiene todos los mensajes de una conversación específica."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mensajes WHERE conversation_id = ? AND user_id = ? ORDER BY created_at ASC", (conversation_id, user_id))
    results = {"messages": [dict(r) for r in cur.fetchall()]}
    conn.close()
    return results

@app.post("/user/{user_id}/conversations")
def create_conversation(user_id: str):
    """Crea una nueva conversación para el usuario."""
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
    last_id = cur.lastrowid
    conn.close()
    return {"id": last_id, "user_id": user_id, "es_flag": es_flag, "created_at": now}

@app.post("/user/{user_id}/conversations/{conversation_id}/messages")
def save_message(user_id: str, conversation_id: int, data: NewMessage):
    """Guarda un mensaje en una conversación."""
    conn = get_db()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    cur.execute("INSERT INTO mensajes (conversation_id, user_id, rol, contenido, created_at) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, user_id, data.rol, data.contenido, now))
    conn.commit()
    conn.close()
    return {"status": "ok", "conversation_id": conversation_id, "user_id": user_id,
            "rol": data.rol, "contenido": data.contenido, "created_at": now}

@app.get("/business/{business_id}/products")
def get_products(business_id: str):
    """Obtiene todos los productos de un negocio."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE business_id = ?", (business_id,))
    results = [dict(r) for r in cur.fetchall()]
    conn.close()
    return results

@app.post("/business/{business_id}/products")
def create_product(business_id: str, data: ProductCreate):
    """Crea un nuevo producto para un negocio."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO products (business_id, name, price, description, image)
        VALUES (?, ?, ?, ?, ?)
    """, (business_id, data.name, data.price, data.description, data.image))
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    
    # Verificar alertas de usuarios (si el context_manager está disponible)
    try:
        if context_manager and context_manager.db:
            cur2 = get_db().cursor()
            cur2.execute("SELECT name FROM businesses WHERE id = ?", (business_id,))
            biz = cur2.fetchone()
            biz_name = biz["name"] if biz else "un negocio"
            context_manager.db.verificar_alertas("vendedor", data.name, biz_name)
            cur2.close()
    except Exception as e:
        print(f"⚠️ Error al verificar alertas: {e}", flush=True)
    
    return {"status": "ok", "id": last_id}

@app.post("/user/{user_id}/business/by_bounds")
def businesses_by_bounds(user_id: str, payload: dict = Body(...)):
    """Obtiene negocios dentro de los límites del mapa de forma segura."""
    # 🚀 CORRECCIÓN CRÍTICA: Extrae 'bounds' si existe, si no, usa el payload raíz
    bounds = payload.get("bounds", payload)
    
    # Extraer esquinas de forma segura con diccionarios de Leaflet nativos
    sw = bounds.get("_southWest")
    ne = bounds.get("_northEast")
    
    # Validación de seguridad: si el formato no es el correcto, evita romper el hilo
    if not sw or not ne:
        return {"businesses": [], "warning": "Estructura de límites inválida"}
        
    min_lat, min_lng = sw.get("lat"), sw.get("lng")
    max_lat, max_lng = ne.get("lat"), ne.get("lng")
    
    # Evitar fallos si alguna coordenada viene corrupta o nula
    if None in (min_lat, min_lng, max_lat, max_lng):
        return {"businesses": [], "warning": "Coordenadas incompletas"}
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM businesses
        WHERE lat BETWEEN ? AND ?
        AND lng BETWEEN ? AND ?
    """, (min_lat, max_lat, min_lng, max_lng))
    
    results = {"businesses": [dict(r) for r in cur.fetchall()]}
    conn.close()
    return results

@app.get("/user/{user_id}/business/nearby")
def get_nearby_businesses(user_id: str, lat: float, lng: float, radius_km: float = 1.0):
    """Obtiene negocios cercanos a una ubicación."""
    delta = radius_km / 111.0
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM businesses
        WHERE lat BETWEEN ? AND ?
        AND lng BETWEEN ? AND ?
    """, (lat - delta, lat + delta, lng - delta, lng + delta))
    results = {"businesses": [dict(r) for r in cur.fetchall()]}
    conn.close()
    return results

@app.post("/user/{user_id}/location")
def set_location(user_id: str, data: dict, db = Depends(get_db)):
    """Actualiza la ubicación del usuario."""
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
    cur.close()
    return {"status": "ok"}

@app.post("/user/{user_id}/comm/status")
def update_comm_status(user_id: str, data: CommStatusUpdate):
    """Actualiza el estado de comunicación del usuario."""
    try:
        if context_manager and context_manager.db:
            context_manager.db.update_comm_status(user_id, data.status, data.social_links)
            return {"status": "ok"}
        return {"status": "error", "msg": "DB adapter not available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user/{user_id}/comm/info")
def get_comm_info(user_id: str):
    """Obtiene información de comunicación del usuario."""
    try:
        if context_manager and context_manager.db:
            info = context_manager.db.get_user_comm_info(user_id)
            if not info:
                raise HTTPException(status_code=404, detail="User communication info not found")
            return info
        return {"status": "error", "msg": "DB adapter not available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/auth/google")
async def auth_google(authorization: str = Header(None)):
    """Autentica usuario con Google Firebase."""
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

@app.get("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "2.0.1",
        "orchestrator_loaded": orchestrator_instance is not None,
        "context_manager_loaded": context_manager is not None
    }
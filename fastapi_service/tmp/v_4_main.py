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

# COPILOT-add:
# Inicializar ContextManager global para gestionar memoria conversacional
# Esto asegura que el contexto se mantenga a lo largo de múltiples interacciones
context_manager = None

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
        db_conn = get_db()
        context_manager = ContextManager(
            db=db_conn,
            max_lines=5,
            rag=None,        # Se puede configurar después si ChromaDB está disponible
            embedder=None,   # Se puede configurar después si está disponible
            query_adapter=None
        )
        print("✅ ContextManager inicializado correctamente", flush=True)
    except Exception as e:
        print(f"⚠️ Error inicializando ContextManager: {e}", flush=True)
        context_manager = None
    
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
CRITICAL_STATES = {"CLOSE_WAIT", "TIME_WAIT", "FIN_WAIT1", "FIN_WAIT2"}
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
    user_id: str
    conversation_id: int | None = None
    message: str

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

@dataclass
class WorkerData:
    rol: str
    datos_db: Dict[str, Any]
    datos_rag: str
    contexto: list
    memoria: list

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
# Helpers
# ---------------------------------------------------------
# async def guardar_contexto(user_id, conversation_id, user_message, ai_message, estado: str | None = None):
#    payload = {"user_id": user_id, "conversation_id": conversation_id, "user_message": user_message, "ai_message": ai_message, "estado": estado}
#    async with httpx.AsyncClient(timeout=300.0) as client:
#        await client.post(f"{WORKER_URL}/context/save", json=payload)

async def fetch_worker_data(user_id: str, message: str, conversation_id: int | None, location: str | None) -> WorkerData:
    payload = {"user_id": user_id, "conversation_id": conversation_id, "message": str(message), "location": location}
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(f"{WORKER_URL}/infer", json=payload)
            datos = r.json().get("response", {})
    except Exception:
        datos = {}
    return WorkerData(
        rol=datos.get("rol", "comprador"),
        datos_db=datos.get("datos_db", {}),
        datos_rag=datos.get("datos_rag", ""),
        contexto=datos.get("contexto", []),
        memoria=datos.get("memoria", [])
    )

def build_prompt_vars(rol: str, datos_db: Dict[str, Any], datos_rag: str, contexto: list, message: str, memoria: list) -> Dict[str, Any]:
    rag_limpio = datos_rag[-400:] if datos_rag else "Inicio de conversación limpia."
    
    # COPILOT-Change:
    # Se convierte memoria (list) a string para que sea compatible con el prompt
    # Esto asegura que el historial conversacional se incluya correctamente en el prompt
    memoria_str = "\n".join(memoria) if memoria and isinstance(memoria, list) else ""
    
    return {"rol": rol, "datos_db": datos_db, "datos_rag": rag_limpio, "contexto": contexto[-5:], "message": message, "memoria": memoria_str}

# COPILOT-Change:
# Se actualiza la función para recibir contexto previo
# Esto permite que la detección de intención sea consciente del historial
# Antes: Recibía solo mensaje
# Ahora: Recibe mensaje + contexto_previo para detectar intenciones de seguimiento
async def detectar_intencion_remoto(mensaje: str, contexto_previo: str = "") -> str:
    payload = {"mensaje": mensaje}
    
    # COPILOT-add:
    # Incluir contexto en la detección de intención
    # Esto evita que el LLM ignore que ya estábamos en una búsqueda COMPRA
    if contexto_previo:
        payload["contexto"] = contexto_previo
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            "http://localhost:9010/infer_intencion",
            json=payload
        )
        data = resp.json()
        return data.get("intencion", "OTRA")

async def registrar_notificacion(user_id: str, tipo: str, item: str):
    # item = mesagge
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE marketplace SET acepta_notificaciones = 1 WHERE user_id = ?", (user_id,))
    cur.execute("INSERT INTO notificaciones (user_id, tipo, mensaje, estado) VALUES (?, ?, ?, 'pendiente')", (user_id, tipo, f"Esperando coincidencias de {item}"))
    conn.commit()
    conn.close()
    async with httpx.AsyncClient(timeout=300.0) as client:
        await client.post("http://mosquitto_service:1883/trigger", json={"user_id": user_id, "tipo": tipo, "item": item})

async def run_mistral_with_prompt(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(f"{MISTRAL_URL}/infer", json={"prompt": prompt, "max_tokens": 384, "temperature": 0.3})
            return r.json().get("response", "Lo siento, tuve un problema técnico.")
    except Exception:
        return "Lo siento, tuve un problema técnico."

# ---------------------------------------------------------
# Orchestrate
# ---------------------------------------------------------
async def orchestrate(user_id: str, message: str, conversation_id: int | None = None, location: str | None = None) -> str:
    # -----------------------------------------------------
    # 0. Obtener datos del worker (mercancia, rol, rag, etc.)
    # -----------------------------------------------------
    datos = await fetch_worker_data(user_id, message, conversation_id, location)

    contenido = datos.datos_db.get("content", [])
    mercancia = datos.datos_db.get("mercancia", "")

    # -----------------------------------------------------
    # 1. INTENCIÓN (solo vía intent_service)
    # -----------------------------------------------------
    # Aquí NO se llama a detectar_intencion_semantica directamente.
    # El intent_service ya integra:
    #   - motor semántico
    #   - fallback keywords
    #   - validación LLM
    intencion = await detectar_intencion_remoto(message)
    print(f"🔍 Intención detectada: {intencion}", flush=True)

    # -----------------------------------------------------
    # 2. Obtener último estado SOLO de esta conversación
    # -----------------------------------------------------
    ultimo_estado = None
    contexto_actual = []

    if datos.contexto:
        for c in datos.contexto:
            if isinstance(c, dict) and c.get("conversation_id") == conversation_id:
                contexto_actual.append(c)

    if contexto_actual:
        for c in reversed(contexto_actual):
            if "estado" in c:
                ultimo_estado = c["estado"]
                print(f">>> Último estado (solo conversación actual): {ultimo_estado}", flush=True)
                break

    # COPILOT: 
    # Si el mensaje es de seguimiento y no trae una intención clara,
    # reutilizamos la última intención principal de la conversación.
    if ultimo_estado and intencion in {"INFORMATIVA", "OTRA"}:
        estado_a_intencion = {
            "COMPRA": "COMPRA",
            "COMPRA_SIN_RESULTADOS": "COMPRA",
            "VENTA": "VENTA",
            "VENTA_SIN_RESULTADOS": "VENTA",
            "TRANSPORTE": "TRANSPORTE",
            "TRANSPORTE_SIN_RESULTADOS": "TRANSPORTE",
            "SERVICIO": "SERVICIO",
            "MENSAJERIA": "MENSAJERIA",
            "NEGOCIO": "NEGOCIO",
            "CONTACTO": "CONTACTO"
        }
        if ultimo_estado in estado_a_intencion:
            print(f">>> Reutilizando intención previa: {estado_a_intencion[ultimo_estado]}", flush=True)
            intencion = estado_a_intencion[ultimo_estado]

    # -----------------------------------------------------
    # 3. Helpers internos
    # -----------------------------------------------------
    def build_prompt(nombre_archivo: str) -> str:
        return PromptBuilder(
            Path(f"{BASE_PRT}/{nombre_archivo}").read_text(encoding="utf-8"),
            build_prompt_vars(
                datos.rol,
                datos.datos_db,
                datos.datos_rag,
                datos.contexto,
                # COPILOT-Change:
                # Orden de parámetros corregido: message debe ir antes de memoria
                # Antes: (datos.rol, datos.datos_db, datos.datos_rag, datos.contexto, datos.memoria, message)
                # Ahora: (datos.rol, datos.datos_db, datos.datos_rag, datos.contexto, message, datos.memoria)
                message,
                datos.memoria
            )
        ).build()

    def normalizar(texto: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFD", texto.lower())
            if unicodedata.category(c) != "Mn"
        )

    def filtrar_contenido(contenido, mercancia):
        if not mercancia:
            return contenido
        merc_norm = normalizar(mercancia)
        return [
            item for item in contenido
            if normalizar(item.get("mercancia", "")) == merc_norm
        ]

    contenido_filtrado = filtrar_contenido(contenido, mercancia)

    # -----------------------------------------------------
    # 4. Lógica por intención
    # -----------------------------------------------------
    estado = None
    respuesta = ""

    # ------------------ COMPRA ------------------
    if intencion == "COMPRA":
        if not contenido_filtrado:
            respuesta = (
                "No hay vendedores activos para la mercancía solicitada.\n"
                "Puedes registrarte como comprador y te avisaré cuando aparezcan vendedores.\n"
            )
            estado = "COMPRA_SIN_RESULTADOS"
        else:
            prompt_base = "broker_prompt_vendedor.txt"
            prompt_completo = build_prompt(prompt_base)
            prompt_reducido = PromptReducerUltra(
                content=contenido_filtrado,
                contexto_previo = datos.memoria,
                message=message,
                role_broker="vendedor",
            ).reduce(prompt_completo)
            # respuesta = await run_mistral_with_prompt(prompt_reducido)
            
            # Crear un futuro para recibir la respuesta
            future = asyncio.get_event_loop().create_future()

            # Enviar el trabajo a la cola
            await cola_modelo.put((prompt_reducido, future))

            # Esperar la respuesta del worker
            respuesta = await future

            estado = "COMPRA"

    # ------------------ VENTA ------------------
    elif intencion == "VENTA":
        if not contenido_filtrado:
            respuesta = (
                "No hay compradores activos para tu producto.\n"
                "Puedes registrarte como vendedor y te avisaré cuando aparezcan interesados.\n"
            )
            estado = "VENTA_SIN_RESULTADOS"
        else:
            prompt_base = "broker_prompt_comprador.txt"
            prompt_completo = build_prompt(prompt_base)
            prompt_reducido = PromptReducerUltra(
                content=contenido_filtrado,
                contexto_previo = datos.memoria,
                message=message,
                role_broker="comprador",
            ).reduce(prompt_completo)
            # respuesta = await run_mistral_with_prompt(prompt_reducido)
            
            # Crear un futuro para recibir la respuesta
            future = asyncio.get_event_loop().create_future()

            # Enviar el trabajo a la cola
            await cola_modelo.put((prompt_reducido, future))

            # Esperar la respuesta del worker
            respuesta = await future
            
            estado = "VENTA"

    # ------------------ TRANSPORTE ------------------
    elif intencion == "TRANSPORTE":
        prompt_base = "prompt_transporte.txt"
        prompt_completo = build_prompt(prompt_base)
        prompt_reducido = PromptReducerUltra(
            content=contenido_filtrado,
            contexto_previo = datos.memoria,
            message=message,
            role_broker="transporte",
        ).reduce(prompt_completo)
        # respuesta = await run_mistral_with_prompt(prompt_reducido)
            
        # Crear un futuro para recibir la respuesta
        future = asyncio.get_event_loop().create_future()

        # Enviar el trabajo a la cola
        await cola_modelo.put((prompt_reducido, future))

        # Esperar la respuesta del worker
        respuesta = await future
        
        estado = "TRANSPORTE"

    # ------------------ SERVICIO ------------------
    elif intencion == "SERVICIO":
        prompt = build_prompt("prompt_servicio.txt")
        # respuesta = await run_mistral_with_prompt(prompt)
            
        # Crear un futuro para recibir la respuesta
        future = asyncio.get_event_loop().create_future()

        # Enviar el trabajo a la cola
        await cola_modelo.put((prompt, future))

        # Esperar la respuesta del worker
        respuesta = await future

        estado = "SERVICIO"

    # ------------------ INFORMACIÓN ------------------
    elif intencion == "INFORMACION":
        prompt = build_prompt("prompt_informativo.txt")
        # respuesta = await run_mistral_with_prompt(prompt)
            
        # Crear un futuro para recibir la respuesta
        future = asyncio.get_event_loop().create_future()

        # Enviar el trabajo a la cola
        await cola_modelo.put((prompt, future))

        # Esperar la respuesta del worker
        respuesta = await future

        estado = "INFORMACION"

    # ------------------ NEGOCIO ------------------
    elif intencion == "NEGOCIO":
        prompt = build_prompt("prompt_negocio.txt")
        # respuesta = await run_mistral_with_prompt(prompt)
            
        # Crear un futuro para recibir la respuesta
        future = asyncio.get_event_loop().create_future()

        # Enviar el trabajo a la cola
        await cola_modelo.put((prompt, future))

        # Esperar la respuesta del worker
        respuesta = await future

        estado = "NEGOCIO"

    # ------------------ CONTACTO ------------------
    elif intencion == "CONTACTO":
        prompt = build_prompt("prompt_contacto.txt")
        # respuesta = await run_mistral_with_prompt(prompt)
            
        # Crear un futuro para recibir la respuesta
        future = asyncio.get_event_loop().create_future()

        # Enviar el trabajo a la cola
        await cola_modelo.put((prompt, future))

        # Esperar la respuesta del worker
        respuesta = await future

        estado = "CONTACTO"

    # ------------------ MENSAJERÍA ------------------
    elif intencion == "MENSAJERIA":
        prompt = build_prompt("prompt_mensajeria.txt")
        # respuesta = await run_mistral_with_prompt(prompt)
            
        # Crear un futuro para recibir la respuesta
        future = asyncio.get_event_loop().create_future()

        # Enviar el trabajo a la cola
        await cola_modelo.put((prompt, future))

        # Esperar la respuesta del worker
        respuesta = await future

        estado = "MENSAJERIA"

    # ------------------ NOTIFICACIÓN ------------------
    elif intencion == "NOTIFICACION":
        prompt = build_prompt("prompt_notificacion.txt")
        # respuesta_base = await run_mistral_with_prompt(prompt)
            
        # Crear un futuro para recibir la respuesta
        future = asyncio.get_event_loop().create_future()

        # Enviar el trabajo a la cola
        await cola_modelo.put((prompt, future))

        # Esperar la respuesta del worker
        respuesta_base = await future

        if ultimo_estado == "COMPRA_SIN_RESULTADOS":
            await registrar_notificacion(user_id, "COMPRA", mercancia)
            respuesta = f"{respuesta_base}\nPerfecto, te avisaré cuando aparezcan vendedores."
            estado = "ESPERA_NOTIFICACION_COMPRA"

        elif ultimo_estado == "VENTA_SIN_RESULTADOS":
            await registrar_notificacion(user_id, "VENTA", mercancia)
            respuesta = f"{respuesta_base}\nPerfecto, te avisaré cuando aparezcan compradores."
            estado = "ESPERA_NOTIFICACION_VENTA"

        elif ultimo_estado == "TRANSPORTE_SIN_RESULTADOS":
            await registrar_notificacion(user_id, "TRANSPORTE", mercancia or message)
            respuesta = f"{respuesta_base}\nPerfecto, te avisaré cuando aparezcan opciones de transporte."
            estado = "ESPERA_NOTIFICACION_TRANSPORTE"

        else:
            respuesta = f"{respuesta_base}\nNo tengo pendiente ninguna notificación para activar."
            estado = "NOTIFICACION_INVALIDA"

    # ------------------ ACLARAR INTENCIÓN ------------------
    elif intencion == "ACLARAR_INTENCION":

        # Si hay contenido filtrado, inferimos si es compra o venta
        if contenido_filtrado and mercancia:
            tipos = {item.get("Tipo", "").lower() for item in contenido_filtrado}
            if "vendedor" in tipos:
                intencion = "COMPRA"
            elif "comprador" in tipos:
                intencion = "VENTA"

        # Reprocesar según nueva intención
        if intencion == "COMPRA":
            prompt_base = "broker_prompt_vendedor.txt"
            prompt_completo = build_prompt(prompt_base)
            prompt_reducido = PromptReducerUltra(
                content=contenido_filtrado,
                contexto_previo = datos.memoria,
                message=message,
                role_broker="vendedor",
            ).reduce(prompt_completo)
            # respuesta = await run_mistral_with_prompt(prompt_reducido)
            
            # Crear un futuro para recibir la respuesta
            future = asyncio.get_event_loop().create_future()

            # Enviar el trabajo a la cola
            await cola_modelo.put((prompt_reducido, future))

            # Esperar la respuesta del worker
            respuesta = await future

            estado = "COMPRA"

        elif intencion == "VENTA":
            prompt_base = "broker_prompt_comprador.txt"
            prompt_completo = build_prompt(prompt_base)
            prompt_reducido = PromptReducerUltra(
                content=contenido_filtrado,
                contexto_previo = datos.memoria,
                message=message,
                role_broker="comprador",
            ).reduce(prompt_completo)
            # respuesta = await run_mistral_with_prompt(prompt_reducido)
            
            # Crear un futuro para recibir la respuesta
            future = asyncio.get_event_loop().create_future()

            # Enviar el trabajo a la cola
            await cola_modelo.put((prompt_reducido, future))

            # Esperar la respuesta del worker
            respuesta = await future

            estado = "VENTA"

        else:
            system_block = (
                "La intención detectada no es clara. Formula una pregunta breve y directa para aclarar si el usuario quiere "
                "COMPRAR o VENDER."
            )
            prompt_final = (
                f"{system_block}\n\n<<USR>>\n{message}\n<<END_USR>>"
            )
            # respuesta = await run_mistral_with_prompt(prompt_final)
            
            # Crear un futuro para recibir la respuesta
            future = asyncio.get_event_loop().create_future()

            # Enviar el trabajo a la cola
            await cola_modelo.put((prompt_final, future))

            # Esperar la respuesta del worker
            respuesta = await future

            estado = "ACLARAR_INTENCION"

    # ------------------ OTRA ------------------
    else:
        prompt = build_prompt("prompt_otra.txt")
        # respuesta = await run_mistral_with_prompt(prompt)
            
        # Crear un futuro para recibir la respuesta
        future = asyncio.get_event_loop().create_future()

        # Enviar el trabajo a la cola
        await cola_modelo.put((prompt, future))

        # Esperar la respuesta del worker
        respuesta = await future

        estado = "OTRA"

    # -----------------------------------------------------
    # Limpieza final
    # -----------------------------------------------------
    # respuesta = re.sub(r"^(IA:\s*)+", "", respuesta.strip(), flags=re.IGNORECASE)
    
    print(f">>>>>>>>> RESPUESTA: {respuesta}\n", flush=True)

    # COPILOT-Change:
    # Se descomenta y activa el guardado de contexto 
    # Antes: Estaba comentado, lo que causaba pérdida de contexto en la 2ª interacción
    # Ahora: Se guarda cada interacción para mantener el historial conversacional
    # await guardar_contexto(user_id, conversation_id, message, respuesta, estado)
    
    # COPILOT-add:
    # Guardar contexto en la base de datos semántica (ChromaDB) y SQLite
    # Esto asegura que el siguiente mensaje tenga acceso al historial completo
    if context_manager:
        try:
            context_manager.save_context(
                user_id=user_id,
                user_msg=message,
                ai_msg=respuesta,
                current_product_query=mercancia
            )
            print(f"✅ Contexto guardado para user {user_id}: {message[:50]}...", flush=True)
        except Exception as e:
            print(f"⚠️ Error al guardar contexto: {e}", flush=True)
    
    return respuesta

# ---------------------------------------------------------
# WebSocket
# ---------------------------------------------------------
modelo_lock = asyncio.Lock()
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    async with modelo_lock:
        await websocket.accept()

        async def heartbeat():
            while True:
                await asyncio.sleep(300)
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
                except WebSocketDisconnect:
                    print("WS: cliente desconectado", flush=True)
                    break  # salir del bucle sin lanzar excepción

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

        finally:
            hb_task.cancel()
            try:
                await websocket.close()
            except Exception:
                pass

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
        r = await client.post(f"{WORKER_URL}/notificacion/leida", json={"notif_id": data.notif_id, "user_id": data.user_id})
    return r.json()

# ---------------------------------------------------------
# Endpoints de conversaciones y mensajes
# ---------------------------------------------------------
@app.get("/conversations/last5")
def get_last5(user_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM conversaciones WHERE user_id = ? ORDER BY created_at DESC LIMIT 5", (user_id,))
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
    cur.execute("INSERT INTO conversaciones (user_id, titulo, es_flag, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (data.user_id, None, es_flag, now, now))
    conn.commit()
    return {"id": cur.lastrowid, "user_id": data.user_id, "es_flag": es_flag, "created_at": now}

@app.post("/messages")
def save_message(data: NewMessage):
    conn = get_db()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    cur.execute("INSERT INTO mensajes (conversation_id, user_id, rol, contenido, created_at) VALUES (?, ?, ?, ?, ?)",
                (data.conversation_id, data.user_id, data.rol, data.contenido, now))
    conn.commit()
    return {"status": "ok", "conversation_id": data.conversation_id, "user_id": data.user_id,
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

# ---------------------------------------------------------
# Ubicación de usuario
# ---------------------------------------------------------
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

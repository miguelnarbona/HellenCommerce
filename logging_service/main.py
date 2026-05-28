import asyncio
import os
import sys
import json
import logging
import sqlite3
import platform
import httpx
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ============================================================
# CONFIGURACIÓN
# ============================================================
EXTERNAL_LLM_URL    = os.getenv("EXTERNAL_LLM_URL",    "https://api.anthropic.com/v1/messages")
EXTERNAL_LLM_KEY    = os.getenv("EXTERNAL_LLM_KEY",    "")
EXTERNAL_LLM_MODEL  = os.getenv("EXTERNAL_LLM_MODEL",  "claude-3-5-sonnet-20241022")
ADMIN_NOTIFY_WEBHOOK= os.getenv("ADMIN_NOTIFY_WEBHOOK", "")   # Slack / N8N / etc.

system = platform.system()
if system == "Windows":
    LOGS_DB_PATH = os.getenv("LOGS_DB_PATH", "c:/HellenData/logs/hellen_logs.db")
else:
    LOGS_DB_PATH = os.getenv("LOGS_DB_PATH", "/app/logs/hellen_logs.db")

# ============================================================
# BASE DE DATOS DE LOGS (SQLite)
# ============================================================
def get_db() -> sqlite3.Connection:
    """Conexión segura para cada hilo/tarea."""
    conn = sqlite3.connect(LOGS_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Crea el esquema si no existe."""
    os.makedirs(os.path.dirname(LOGS_DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS logs (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp         TEXT NOT NULL,
            log_level         TEXT NOT NULL,
            service_origin    TEXT NOT NULL,
            source_file       TEXT,
            line_number       INTEGER,
            file_path         TEXT,
            code_snippet      TEXT,
            error_description TEXT,
            proposed_solution TEXT,
            status_flag       TEXT DEFAULT 'SOLUCIONADO',
            created_at        TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS hotfix_queue (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            log_id            INTEGER REFERENCES logs(id),
            service_origin    TEXT NOT NULL,
            source_file       TEXT,
            line_number       INTEGER,
            error_description TEXT,
            proposed_solution TEXT,
            proposed_code     TEXT,
            ai_model_used     TEXT,
            status            TEXT DEFAULT 'PENDIENTE',
            approved_by       TEXT,
            approved_at       TEXT,
            applied_at        TEXT,
            created_at        TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    print(">>> Logs DB inicializada correctamente.")

def persist_log(payload: dict) -> int:
    """Guarda el log en la base de datos y retorna el id generado."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO logs (
            timestamp, log_level, service_origin, source_file,
            line_number, file_path, code_snippet,
            error_description, proposed_solution, status_flag
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        payload.get("timestamp", datetime.utcnow().isoformat()),
        payload.get("log_level", "INFO"),
        payload.get("service_origin", "unknown"),
        payload.get("source_file", ""),
        payload.get("line_number", 0),
        payload.get("file_path", ""),
        payload.get("code_snippet", ""),
        payload.get("error_description", ""),
        payload.get("proposed_solution", ""),
        payload.get("status_flag", "SOLUCIONADO"),
    ))
    conn.commit()
    log_id = cur.lastrowid
    conn.close()
    return log_id

def persist_hotfix(log_id: int, payload: dict, proposed_code: str, ai_model: str):
    """Crea un ticket en la cola de hot-fix."""
    conn = get_db()
    conn.execute("""
        INSERT INTO hotfix_queue (
            log_id, service_origin, source_file, line_number,
            error_description, proposed_solution, proposed_code, ai_model_used, status
        ) VALUES (?,?,?,?,?,?,?,?,'PENDIENTE')
    """, (
        log_id,
        payload.get("service_origin", ""),
        payload.get("source_file", ""),
        payload.get("line_number", 0),
        payload.get("error_description", ""),
        payload.get("proposed_solution", ""),
        proposed_code,
        ai_model,
    ))
    conn.commit()
    conn.close()

# ============================================================
# GESTOR DE CONEXIONES ACTIVAS (Admin Dashboard)
# ============================================================
class AdminBroadcaster:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self.connections = [c for c in self.connections if c != ws]

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

admin_broadcaster = AdminBroadcaster()

# ============================================================
# HOT-FIX PIPELINE (Claude / LLM Externo)
# ============================================================
async def call_external_llm(error_desc: str, code_snippet: str, source_file: str, line_number: int) -> str:
    """
    Llama al LLM externo (Claude) y pide un hot-fix propuesto.
    Retorna el código corregido como string.
    """
    if not EXTERNAL_LLM_KEY:
        return "# [Hot-Fix Mock] No hay API Key configurada. Fix manual requerido."

    system_prompt = (
        "Eres un experto en debugging y Python. "
        "Recibirás una descripción de error y el fragmento de código que lo causó. "
        "Tu tarea es proponer el código corregido MÍNIMAMENTE, sin agregar imports innecesarios. "
        "Responde SOLO con el bloque de código corregido entre triple backtick python."
    )

    user_msg = (
        f"Archivo: {source_file} | Línea: {line_number}\n"
        f"Descripción del error: {error_desc}\n\n"
        f"Fragmento de código problemático:\n```python\n{code_snippet}\n```"
    )

    try:
        headers = {
            "x-api-key": EXTERNAL_LLM_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        body = {
            "model": EXTERNAL_LLM_MODEL,
            "max_tokens": 512,
            "messages": [
                {"role": "user", "content": f"{system_prompt}\n\n{user_msg}"}
            ]
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(EXTERNAL_LLM_URL, headers=headers, json=body)
            data = resp.json()
            content = data.get("content", [{}])[0].get("text", "")
            # Extraer bloque de código
            import re
            match = re.search(r"```python(.*?)```", content, re.DOTALL)
            if match:
                return match.group(1).strip()
            return content.strip()
    except Exception as e:
        return f"# [Hot-Fix Error] Fallo al contactar LLM externo: {e}"

async def hotfix_pipeline(log_id: int, payload: dict):
    """
    1. Llama al LLM externo para proponer la corrección.
    2. Persiste el ticket en hotfix_queue con status=PENDIENTE.
    3. Transmite al Admin Dashboard para aprobación humana.
    """
    error_desc   = payload.get("error_description", "Error desconocido")
    code_snippet = payload.get("code_snippet", "")
    source_file  = payload.get("source_file", "unknown")
    line_number  = payload.get("line_number", 0)
    service      = payload.get("service_origin", "unknown")

    print(f"[HotFix] Iniciando pipeline para {service}:{source_file}:{line_number}", flush=True)

    proposed_code = await call_external_llm(error_desc, code_snippet, source_file, line_number)

    persist_hotfix(log_id, payload, proposed_code, EXTERNAL_LLM_MODEL)

    # Notificar al Admin Dashboard para aprobación humana
    alert = {
        "type":             "HOTFIX_PENDING",
        "log_id":           log_id,
        "service_origin":   service,
        "source_file":      source_file,
        "line_number":      line_number,
        "error_description":error_desc,
        "proposed_code":    proposed_code,
        "status":           "PENDIENTE",
        "created_at":       datetime.utcnow().isoformat()
    }
    await admin_broadcaster.broadcast(alert)

    # Webhook externo (Slack / N8N) si configurado
    if ADMIN_NOTIFY_WEBHOOK:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(ADMIN_NOTIFY_WEBHOOK, json=alert)
        except Exception:
            pass

    print(f"[HotFix] Ticket PENDIENTE creado para {service}. Esperando aprobación humana.", flush=True)

# ============================================================
# STARTUP / LIFESPAN
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print(">>> Subsistema de Logging & Self-Healing listo.", flush=True)
    yield
    print(">>> Logging Service apagándose.")

# ============================================================
# APP
# ============================================================
app = FastAPI(title="Logging & Self-Healing Subsystem", lifespan=lifespan)

# ============================================================
# WS 1: Ingress de logs provenientes de todos los microservicios
# ============================================================
@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    """
    Recibe logs estructurados JSON de cada microservicio.
    Persiste en DB, retransmite al Dashboard y activa Hot-Fix en ERROR/WARNING.
    """
    await websocket.accept()
    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect as e:
                print(f"WS cerrado por el cliente ({e.code})", flush=True)
                break  # salir del bucle sin error

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # 1. Persistir log
            log_id = await asyncio.to_thread(persist_log, payload)

            # 2. Broadcast tiempo real al Dashboard
            await admin_broadcaster.broadcast({
                "type":    "LOG",
                "log_id":  log_id,
                **payload
            })

            # 3. Si es ERROR o WARNING → Hot-Fix pipeline (asíncrono, no bloquea)
            if payload.get("log_level") in ("ERROR", "WARNING"):
                asyncio.create_task(hotfix_pipeline(log_id, payload))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[Logging WS Error] {e}", flush=True)

# ============================================================
# WS 2: Admin Dashboard (lectura de alertas en tiempo real)
# ============================================================
@app.websocket("/ws/admin")
async def ws_admin(websocket: WebSocket):
    """
    El Admin Dashboard se conecta aquí para recibir logs
    y tickets de hot-fix en tiempo real.
    """
    await admin_broadcaster.connect(websocket)
    try:
        while True:
            # Mantener la conexión viva; el Dashboard solo escucha
            await asyncio.sleep(30)
            await websocket.send_json({"type": "PING"})
    except WebSocketDisconnect:
        admin_broadcaster.disconnect(websocket)

# ============================================================
# REST API: Consulta de logs y gestión de hot-fixes
# ============================================================

@app.get("/logs")
async def get_logs(
    service: Optional[str] = None,
    level:   Optional[str] = None,
    limit:   int = 100
):
    """Devuelve los últimos N logs, filtrable por servicio y nivel."""
    conn = get_db()
    query = "SELECT * FROM logs WHERE 1=1"
    params = []
    if service:
        query += " AND service_origin = ?"
        params.append(service)
    if level:
        query += " AND log_level = ?"
        params.append(level.upper())
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/hotfixes")
async def get_hotfixes(status: Optional[str] = None):
    """Devuelve la cola de hot-fixes, filtrable por status."""
    conn = get_db()
    query = "SELECT * FROM hotfix_queue WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status.upper())
    query += " ORDER BY id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

class ApprovalRequest(BaseModel):
    approved_by: str

@app.post("/hotfixes/{hotfix_id}/approve")
async def approve_hotfix(hotfix_id: int, req: ApprovalRequest):
    """
    El administrador aprueba un hot-fix.
    Cambia status → APROBADO. La aplicación del parche es tarea del CI/CD.
    """
    conn = get_db()
    cur = conn.execute(
        "SELECT * FROM hotfix_queue WHERE id = ?", (hotfix_id,)
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Hot-fix no encontrado")

    conn.execute("""
        UPDATE hotfix_queue
        SET status      = 'APROBADO',
            approved_by = ?,
            approved_at = ?
        WHERE id = ?
    """, (req.approved_by, datetime.utcnow().isoformat(), hotfix_id))
    conn.commit()
    conn.close()

    # Notificar al Dashboard
    await admin_broadcaster.broadcast({
        "type":      "HOTFIX_APPROVED",
        "hotfix_id": hotfix_id,
        "approved_by": req.approved_by
    })
    return {"status": "APROBADO", "hotfix_id": hotfix_id}

@app.post("/hotfixes/{hotfix_id}/reject")
async def reject_hotfix(hotfix_id: int, req: ApprovalRequest):
    """Rechaza un hot-fix propuesto."""
    conn = get_db()
    conn.execute("""
        UPDATE hotfix_queue
        SET status      = 'RECHAZADO',
            approved_by = ?,
            approved_at = ?
        WHERE id = ?
    """, (req.approved_by, datetime.utcnow().isoformat(), hotfix_id))
    conn.commit()
    conn.close()

    await admin_broadcaster.broadcast({
        "type":      "HOTFIX_REJECTED",
        "hotfix_id": hotfix_id
    })
    return {"status": "RECHAZADO", "hotfix_id": hotfix_id}

@app.post("/hotfixes/{hotfix_id}/applied")
async def mark_applied(hotfix_id: int):
    """Marca un hot-fix como APLICADO (llamado por el pipeline CI/CD)."""
    conn = get_db()
    conn.execute("""
        UPDATE hotfix_queue
        SET status     = 'APLICADO',
            applied_at = ?
        WHERE id = ?
    """, (datetime.utcnow().isoformat(), hotfix_id))
    conn.commit()
    conn.close()
    return {"status": "APLICADO", "hotfix_id": hotfix_id}

@app.get("/stats")
async def get_stats():
    """Resumen de salud del sistema basado en los logs."""
    conn = get_db()
    total   = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
    errors  = conn.execute("SELECT COUNT(*) FROM logs WHERE log_level='ERROR'").fetchone()[0]
    warnings= conn.execute("SELECT COUNT(*) FROM logs WHERE log_level='WARNING'").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM hotfix_queue WHERE status='PENDIENTE'").fetchone()[0]
    approved= conn.execute("SELECT COUNT(*) FROM hotfix_queue WHERE status='APROBADO'").fetchone()[0]
    applied = conn.execute("SELECT COUNT(*) FROM hotfix_queue WHERE status='APLICADO'").fetchone()[0]
    conn.close()
    return {
        "total_logs":         total,
        "errors":             errors,
        "warnings":           warnings,
        "hotfixes_pending":   pending,
        "hotfixes_approved":  approved,
        "hotfixes_applied":   applied,
        "system_health":      "DEGRADED" if errors > 0 else "OK"
    }

@app.get("/health")
def health():
    return {"status": "ok"}

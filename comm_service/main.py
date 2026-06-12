from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
import httpx
import platform
import os
import datetime
import sqlite3
import json
from typing import List, Optional
from chromadb import HttpClient

app = FastAPI(title="HellenCommerce Communication Service", version="1.0.0")

# Configuración
system = platform.system() 

if  system == 'Windows':   
    SQLITE_PATH = os.getenv(
        "SQLITE_PATH",
        "c:\HellenCommerce\HellenData\hellencommerce.db"
    )
else: 
    SQLITE_PATH = os.getenv(
        "SQLITE_PATH",
        "/models/HellenData/hellencommerce.db"
    )

# SQLITE_PATH = os.getenv("SQLITE_PATH", "c:/HellenCommerce/HellenData/hellencommerce.db")
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", 8001))

# Inicializar ChromaDB
try:
    chroma_client = HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = chroma_client.get_or_create_collection(name="user_conversations")
    print(f"✅ Conectado a ChromaDB en {CHROMA_HOST}:{CHROMA_PORT}")
except Exception as e:
    print(f"⚠️ Error conectando a ChromaDB: {e}")
    collection = None

class Message(BaseModel):
    sender_id: str
    receiver_id: str
    text: str
    type: str = "chat"  # chat, email, whatsapp

class StatusUpdate(BaseModel):
    status: str
    social_links: Optional[dict] = None

def get_db():
    conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/health")
def health():
    return {"status": "ok", "service": "comm_service"}

@app.post("/send")
async def send_message(msg: Message):
    # 1. Validar usuarios (opcional, por simplicidad asumimos que existen)
    
    # 2. Guardar en SQLite (Historial persistente)
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO notificaciones (user_id, tipo, mensaje, estado)
            VALUES (?, ?, ?, 'enviada')
        """, (msg.receiver_id, msg.type, f"Mensaje de {msg.sender_id}: {msg.text}"))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error guardando en SQLite: {e}")

    # 3. Indexar en ChromaDB para memoria semántica
    if collection:
        try:
            timestamp = datetime.datetime.utcnow().isoformat()
            doc_id = f"msg_{msg.sender_id}_{msg.receiver_id}_{int(datetime.datetime.utcnow().timestamp())}"
            collection.add(
                documents=[msg.text],
                metadatas=[{
                    "sender": msg.sender_id,
                    "receiver": msg.receiver_id,
                    "type": msg.type,
                    "timestamp": timestamp
                }],
                ids=[doc_id]
            )
            print(f"📥 Mensaje indexado en ChromaDB: {doc_id}")
        except Exception as e:
            print(f"Error indexando en ChromaDB: {e}")

    return {"status": "sent", "timestamp": datetime.datetime.utcnow().isoformat()}

@app.get("/history/{user_id}")
def get_history(user_id: str, other_id: Optional[str] = None):
    # Por ahora simulado o consulta simple a SQLite
    return {"history": []}

@app.post("/status/{user_id}")
def update_status(user_id: str, data: StatusUpdate):
    try:
        conn = get_db()
        cur = conn.cursor()
        # Intentar actualizar en ambas tablas por si es usuario o negocio
        cur.execute("UPDATE usuarios SET comm_status = ?, social_links = ? WHERE user_id = ?", 
                   (data.status, json.dumps(data.social_links) if data.social_links else None, user_id))
        cur.execute("UPDATE marketplace SET comm_status = ?, social_links = ? WHERE user_id = ?", 
                   (data.status, json.dumps(data.social_links) if data.social_links else None, user_id))
        conn.commit()
        conn.close()
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9005)

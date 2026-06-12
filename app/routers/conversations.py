from fastapi import APIRouter
from pydantic import BaseModel
import sqlite3, datetime

router = APIRouter()

class NewConversation(BaseModel):
    user_id: str

class NewMessage(BaseModel):
    conversation_id: int
    user_id: str
    rol: str
    contenido: str

def get_db():
    conn = sqlite3.connect("conversations.db")
    conn.row_factory = sqlite3.Row
    return conn

@router.get("/conversations/last5")
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

@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mensajes WHERE conversation_id = ? ORDER BY created_at ASC", (conversation_id,))
    return {"messages": [dict(r) for r in cur.fetchall()]}

@router.post("/conversations")
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

@router.post("/messages")
def save_message(data: NewMessage):
    conn = get_db()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    cur.execute("""
        INSERT INTO mensajes (conversation_id, user_id, rol, contenido, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (data.conversation_id, data.user_id, data.rol, data.contenido, now))
    conn.commit()
    return {"status": "ok"}

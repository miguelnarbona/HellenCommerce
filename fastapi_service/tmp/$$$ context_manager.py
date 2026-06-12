import json
import sqlite3
import os

def get_db():
    conn = sqlite3.connect(os.getenv("SQLITE_PATH"))
    conn.row_factory = sqlite3.Row
    return conn

class FastAPIContextManager:

    def load_product_state(self, user_id: str):
        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT product_state FROM usuarios WHERE user_id = ?", (user_id,))
        row = cur.fetchone()

        if row and row["product_state"]:
            return json.loads(row["product_state"])

        return {
            "producto": None,
            "modelo": None,
            "color": None,
            "ubicacion": None,
            "marca": None,
            "precio_min": None,
            "precio_max": None,
            "extras": []
        }

    def save_product_state(self, user_id: str, state: dict):
        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "UPDATE usuarios SET product_state = ? WHERE user_id = ?",
            (json.dumps(state), user_id)
        )
        conn.commit()

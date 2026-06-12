# app/adapters/db/SQLiteAdapter.py

import sqlite3
import json
import os
from pathlib import Path


class SQLiteAdapter:

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.getenv("SQLITE_PATH")
        self._ensure_schema()

    # ============================================================
    # CONEXIÓN
    # ============================================================
    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    # ============================================================
    # CREAR TABLAS SI NO EXISTEN
    # ============================================================
    def _ensure_schema(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        # Tabla de usuarios
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                user_id TEXT PRIMARY KEY,
                tipo TEXT,
                mercancia TEXT,
                estado TEXT,
                current_product_query TEXT,
                product_state TEXT,
                last_vendor TEXT,
                contexto TEXT,
                lat REAL,
                lon REAL, 
                timestamp TEXT
            )
        """)

        # Tabla marketplace
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS marketplace (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                tipo TEXT,                         -- vendedor / comprador
                nombre TEXT,                       -- nombre del negocio o persona
                mercancia TEXT,                    -- producto: helado, cerveza, arroz
                categoria_negocio TEXT,            -- barberia, heladeria, cafeteria
                servicio TEXT,                     -- corte de pelo, reparación
                tags TEXT,                         -- JSON: ["frio","dulce","artesanal"]
                tamaños TEXT,
                precio REAL,
                ubicacion TEXT,
                lat REAL,
                lon REAL,
                telefono TEXT,
                correo TEXT,
                contacto TEXT,
                domicilio INTEGER,
                estado TEXT,
                contexto TEXT,
                timestamp TEXT,
                acepta_notificaciones INTEGER,
                canal TEXT,
                preferencias TEXT,
                current_product_query TEXT,
                product_state TEXT,
                last_vendor TEXT
            )
        """)

        # Tabla de notificaciones
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notificaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                tipo TEXT,
                mensaje TEXT,
                estado TEXT DEFAULT 'pendiente',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_envio TIMESTAMP,
                fecha_lectura TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    # ============================================================
    # REGISTRAR USUARIO
    # ============================================================
    def registrar_usuario(self, data: dict):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO usuarios (
                user_id, tipo, mercancia, estado, current_product_query, timestamp
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            data.get("user_id"),
            data.get("tipo"),
            data.get("mercancia"),
            data.get("estado", "activo"),
            data.get("current_product_query")
        ))

        conn.commit()
        conn.close()

    # ============================================================
    # BUSCAR COINCIDENCIAS EN MARKETPLACE
    # ============================================================
    def buscar_coincidencias(self, tipo, item):
        conn = self._get_conn()
        cursor = conn.cursor()

        # ------------------------------------------------------------
        # BÚSQUEDA EXTENDIDA (mercancia + negocio + servicio + tags)
        # ------------------------------------------------------------
        cursor.execute("""
            SELECT id, user_id, tipo, nombre, mercancia, tamaños, precio, ubicacion,
                telefono, correo, contacto, domicilio, estado, contexto
            FROM marketplace
            WHERE tipo = ?
            AND (
                    mercancia LIKE ?
                    OR categoria_negocio LIKE ?
                    OR servicio LIKE ?
                    OR tags LIKE ?
                )
        """, (
            tipo,
            f"%{item}%",
            f"%{item}%",
            f"%{item}%",
            f"%{item}%"
        ))

        rows = cursor.fetchall()
        conn.close()

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "user_id": r[1],
                "tipo": r[2],
                "nombre": r[3],
                "mercancia": r[4],
                "tamaños": r[5],
                "precio": r[6],
                "ubicacion": r[7],
                "telefono": r[8],
                "correo": r[9],
                "contacto": r[10],
                "domicilio": r[11],
                "estado": r[12],
                "contexto": r[13]
            })

        return results

    # ============================================================
    # HISTORIAL DE USUARIO
    # ============================================================
    def obtener_historial_usuario(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT current_product_query, product_state, last_vendor
            FROM usuarios
            WHERE user_id = ?
        """, (user_id,))

        rows = cursor.fetchall()
        conn.close()

        historial = []
        for r in rows:
            historial.append({
                "current_product_query": r[0],
                "product_state": r[1],
                "last_vendor": json.loads(r[2]) if r[2] else None
            })

        return historial

    # ============================================================
    # 🔥 PERSISTENCIA INTELIGENTE
    # ============================================================
    def update_user_state(self, user_id, current_product_query=None, product_state=None, last_vendor=None):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE usuarios
            SET current_product_query = COALESCE(?, current_product_query),
                product_state = COALESCE(?, product_state),
                last_vendor = COALESCE(?, last_vendor),
                timestamp = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (
            current_product_query,
            product_state,
            json.dumps(last_vendor) if last_vendor is not None else None,
            user_id
        ))

        conn.commit()
        conn.close()

    # ============================================================
    # 🔥 OBTENER ESTADO DEL USUARIO
    # ============================================================
    def get_user_state(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT current_product_query, product_state, last_vendor
            FROM usuarios
            WHERE user_id = ?
        """, (user_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "current_product_query": row[0],
            "product_state": row[1],
            "last_vendor": json.loads(row[2]) if row[2] else None
        }

    # ============================================================
    # 🔥 NOTIFICACIONES — obtener pendientes
    # ============================================================
    def obtener_notificaciones_pendientes(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, user_id, tipo, mensaje, estado, fecha_creacion
            FROM notificaciones
            WHERE estado = 'pendiente'
            ORDER BY fecha_creacion ASC
        """)

        rows = cursor.fetchall()
        conn.close()

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "user_id": r[1],
                "tipo": r[2],
                "mensaje": r[3],
                "estado": r[4],
                "fecha_creacion": r[5]
            })

        return results

    # ============================================================
    # 🔥 NOTIFICACIONES — marcar como enviada
    # ============================================================
    def marcar_notificacion_enviada(self, notif_id):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE notificaciones
            SET estado = 'enviada',
                fecha_envio = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (notif_id,))

        conn.commit()
        conn.close()

    # ============================================================
    # 🔥 NOTIFICACIONES — registrar nueva
    # ============================================================
    def registrar_notificacion(self, user_id, tipo, mensaje):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO notificaciones (user_id, tipo, mensaje, estado)
            VALUES (?, ?, ?, 'pendiente')
        """, (user_id, tipo, mensaje))

        conn.commit()
        conn.close()

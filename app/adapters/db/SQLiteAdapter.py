# app/adapters/db/SQLiteAdapter.py

import sqlite3
import json
import os
import requests
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
    # 🔥 GEOCODIFICACIÓN REAL (OpenStreetMap)
    # ============================================================
    def _geocode(self, texto):
        """
        Convierte texto de ubicación en coordenadas reales usando Nominatim.
        Funciona con repartos, barrios, calles, municipios y provincias.
        """
        if not texto:
            return None, None

        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": f"{texto}, Cuba",
            "format": "json",
            "limit": 1
        }

        try:
            r = requests.get(url, params=params, headers={"User-Agent": "HellenCommerce"})
            data = r.json()
            if len(data) > 0:
                return float(data[0]["lat"]), float(data[0]["lon"])
        except:
            pass

        return None, None

    # ============================================================
    # 🔥 FALLBACK: COORDENADAS POR PROVINCIA
    # ============================================================
    def _coords_from_provincia(self, provincia):
        COORDENADAS_PROVINCIAS = {
            "Pinar del Río": (22.4173, -83.6987),
            "Artemisa": (22.8133, -82.7619),
            "La Habana": (23.1136, -82.3666),
            "Mayabeque": (22.9870, -82.1511),
            "Matanzas": (23.0450, -81.5800),
            "Cienfuegos": (22.1460, -80.4350),
            "Villa Clara": (22.4930, -79.9660),
            "Sancti Spíritus": (21.9300, -79.4420),
            "Ciego de Ávila": (21.8400, -78.7610),
            "Camagüey": (21.3808, -77.9169),
            "Las Tunas": (20.9600, -76.9540),
            "Holguín": (20.8872, -76.2631),
            "Granma": (20.3833, -76.6413),
            "Santiago de Cuba": (20.0200, -75.8290),
            "Guantánamo": (20.1440, -75.2090),
            "Isla de la Juventud": (21.8833, -82.8000)
        }

        if provincia in COORDENADAS_PROVINCIAS:
            return COORDENADAS_PROVINCIAS[provincia]

        return None, None

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
                comm_status TEXT DEFAULT 'online',
                social_links TEXT,
                timestamp TEXT
            )
        """)

        # Tabla marketplace
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS marketplace (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                tipo TEXT,
                nombre TEXT,
                mercancia TEXT,
                categoria_negocio TEXT,
                servicio TEXT,
                tags TEXT,
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
                last_vendor TEXT,
                comm_status TEXT DEFAULT 'online',
                social_links TEXT
            )
        """)

        # Tabla de alertas (intereses de usuarios)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                tipo TEXT,
                item TEXT,
                estado TEXT DEFAULT 'activo',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    # 🔥 NUEVO: REGISTRAR VENDEDOR CON GEOLOCALIZACIÓN REAL
    # ============================================================
    def registrar_vendedor_marketplace(self, data: dict):
        conn = self._get_conn()
        cursor = conn.cursor()

        texto_ubicacion = data.get("ubicacion")

        # 1. Intentar geocodificación real
        lat, lon = self._geocode(texto_ubicacion)

        # 2. Fallback a provincia si falla
        if lat is None:
            lat, lon = self._coords_from_provincia(texto_ubicacion)

        cursor.execute("""
            INSERT INTO marketplace (
                user_id, tipo, nombre, mercancia, categoria_negocio, servicio,
                tags, tamaños, precio, ubicacion, lat, lon, telefono, correo,
                contacto, domicilio, estado, contexto, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            data.get("user_id"),
            "vendedor",
            data.get("nombre"),
            data.get("mercancia"),
            data.get("categoria_negocio"),
            data.get("servicio"),
            json.dumps(data.get("tags")) if data.get("tags") else None,
            data.get("tamaños"),
            data.get("precio"),
            texto_ubicacion,
            lat,
            lon,
            data.get("telefono"),
            data.get("correo"),
            data.get("contacto"),
            data.get("domicilio", 0),
            "activo",
            data.get("contexto")
        ))

        conn.commit()
        conn.close()

        # 🔥 NUEVO: Verificar si hay usuarios esperando por esta mercancía
        try:
            self.verificar_alertas("vendedor", data.get("mercancia", ""), data.get("nombre", "un nuevo negocio"))
        except Exception as e:
            print(f"⚠️ Error al verificar alertas tras registro: {e}", flush=True)

    # ============================================================
    # BUSCAR COINCIDENCIAS EN MARKETPLACE (extendido con lat/lon)
    # ============================================================
    def buscar_coincidencias(self, tipo, item):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, user_id, tipo, nombre, mercancia, tamaños, precio, ubicacion,
                   lat, lon, telefono, correo, contacto, domicilio, estado, contexto
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
                "lat": r[8],
                "lon": r[9],
                "telefono": r[10],
                "correo": r[11],
                "contacto": r[12],
                "domicilio": r[13],
                "estado": r[14],
                "contexto": r[15]
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

    # ============================================================
    # 🔥 ALERTAS — registrar nueva alerta de interés
    # ============================================================
    def registrar_alerta(self, user_id, tipo, item):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO alerts (user_id, tipo, item, estado)
            VALUES (?, ?, ?, 'activo')
        """, (user_id, tipo, item))

        conn.commit()
        conn.close()

    # ============================================================
    # 🔥 ALERTAS — verificar coincidencias
    # ============================================================
    def verificar_alertas(self, tipo_nuevo, item_nuevo, nombre_entidad):
        """
        Busca alertas activas que coincidan con un nuevo item registrado.
        Si hay coincidencia, crea una notificación pendiente para el usuario.
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # tipo_nuevo: si se registró un VENDEDOR, buscamos alertas de COMPRA
        # si se registró un COMPRADOR, buscamos alertas de VENTA
        tipo_alerta_buscada = "COMPRA" if tipo_nuevo.lower() == "vendedor" else "VENTA"

        cursor.execute("""
            SELECT id, user_id, item
            FROM alerts
            WHERE estado = 'activo'
            AND tipo = ?
            AND ? LIKE '%' || item || '%'
        """, (tipo_alerta_buscada, item_nuevo))

        alertas = cursor.fetchall()

        for alerta_id, user_id, item in alertas:
            mensaje = f"¡Buenas noticias! Se ha encontrado {item} en {nombre_entidad}. Revisa el mapa."
            cursor.execute("""
                INSERT INTO notificaciones (user_id, tipo, mensaje, estado)
                VALUES (?, ?, ?, 'pendiente')
            """, (user_id, tipo_alerta_buscada, mensaje))

            # Marcar alerta como notificada para no repetir
            cursor.execute("UPDATE alerts SET estado = 'notificado' WHERE id = ?", (alerta_id,))

        conn.commit()
        conn.close()

    # ============================================================
    # 🔥 COMUNICACIÓN — actualizar estado
    # ============================================================
    def update_comm_status(self, user_id, status, social_links=None):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Actualizar en tabla usuarios
        cursor.execute("""
            UPDATE usuarios 
            SET comm_status = ?, social_links = COALESCE(?, social_links)
            WHERE user_id = ?
        """, (status, json.dumps(social_links) if social_links else None, user_id))
        
        # También actualizar en marketplace si existe como negocio
        cursor.execute("""
            UPDATE marketplace 
            SET comm_status = ?, social_links = COALESCE(?, social_links)
            WHERE user_id = ?
        """, (status, json.dumps(social_links) if social_links else None, user_id))
        
        conn.commit()
        conn.close()

    def get_user_comm_info(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT comm_status, social_links, telefono, correo FROM marketplace WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("SELECT comm_status, social_links FROM usuarios WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                conn.close()
                return None
            conn.close()
            return {"status": row[0], "social_links": json.loads(row[1]) if row[1] else {}}
        
        conn.close()
        return {
            "status": row[0], 
            "social_links": json.loads(row[1]) if row[1] else {},
            "phone": row[2],
            "email": row[3]
        }

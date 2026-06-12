import asyncio
import httpx
import unicodedata
import paho.mqtt.publish as publish
from concurrent.futures import ThreadPoolExecutor
import os
import sqlite3
import math
from typing import Any, Dict
from dataclasses import dataclass
from pathlib import Path

from app.core.pipeline.PromptBuilder import PromptBuilder
from app.core.pipeline.PromptReducerUltra import PromptReducerUltra
import re
import json  # CURSOR-add: serialización en payload CONNECT

import logging
logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=2)

@dataclass
class WorkerData:
    rol: str
    datos_db: Dict[str, Any]
    datos_rag: str
    contexto: list
    memoria: list

def normalizar(texto: str) -> str:
    """
    Normaliza texto removiendo acentos y convirtiendo a minúsculas.
    Útil para comparaciones case-insensitive sin caracteres acentuados.
    """
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )

def sanitize_response(texto: str) -> str:
    """Limpia caracteres basura (como CJK) generados por el LLM y hace strip."""
    if not texto:
        return ""
    texto_limpio = re.sub(r'[\u4e00-\u9fff]+', '', texto)
    return texto_limpio.strip()

def es_nueva_consulta(message: str) -> bool:
    """
    Detecta si el mensaje indica una nueva consulta de compra/venta.
    
    Retorna True si el usuario está iniciando una nueva búsqueda,
    evitando reutilizar mercancía previa innecesariamente.
    """
    palabras_nueva = [
        "tienes", "tendrás", "tendras", "hay", "busco", "quiero", "necesito", 
        "buscando", "vende", "venden", "comprar", "compras", "compra",
        "vendo", "ventas", "venta", "ofrece", "ofrecen", "disponible",
        "podrias", "podrías", "podras", "podrás", "puedes", "puede"
    ]
    message_lower = message.lower()
    return any(palabra in message_lower for palabra in palabras_nueva)

# CURSOR-add: detectar peticiones de navegación / ruta (distinto de pedir teléfono o contacto)
def es_solicitud_ruta(mensaje: str) -> bool:
    msg = normalizar(mensaje)
    patrones_navegacion = [
        r"\bcomo llego\b", r"\bcomo llegar\b", r"\bllegar a\b", r"\bllegar al\b",
        r"\bindicaciones\b", r"\bdireccion\b", r"\bruta\b", r"\bcamino\b",
        r"\bmapa\b", r"\bnavegacion\b", r"\btrazar\b", r"\btrazame\b",
        r"\bdonde queda\b", r"\bir al vendedor\b", r"\bir a la tienda\b",
    ]
    return any(re.search(p, msg) for p in patrones_navegacion)

# CURSOR-add: extraer nombre del vendedor/negocio citado en el mensaje de ruta
def extraer_nombre_destino(mensaje: str) -> str | None:
    patrones = [
        r"vendedor(?:a)?\s+([A-Za-zÁÉÍÓÚáéíóúñÑ][A-Za-zÁÉÍÓÚáéíóúñÑ\s]{2,60})",
        r"llego\s+al?\s+vendedor(?:a)?\s+([A-Za-zÁÉÍÓÚáéíóúñÑ][A-Za-zÁÉÍÓÚáéíóúñÑ\s]{2,60})",
        r"llegar\s+al?\s+vendedor(?:a)?\s+([A-Za-zÁÉÍÓÚáéíóúñÑ][A-Za-zÁÉÍÓÚáéíóúñÑ\s]{2,60})",
    ]
    for patron in patrones:
        m = re.search(patron, mensaje, re.IGNORECASE)
        if m:
            nombre = m.group(1).strip(" ?.,;!")
            if len(nombre) >= 3:
                return nombre
    return None

# CURSOR-add: resolver negocio destino desde búsqueda actual o resultados guardados en contexto
def resolver_best_business(
    message: str,
    location: str | None,
    contenido: list,
    contenido_filtrado: list,
    context_manager,
    user_id: str,
) -> tuple[Any | None, float]:
    search_pool = list(contenido_filtrado) if contenido_filtrado else list(contenido or [])

    if not search_pool and context_manager:
        stored = context_manager.get_search_results(user_id)
        if stored and stored.get("contenido"):
            search_pool = list(stored["contenido"])
            print(f">>> Usando {len(search_pool)} resultados guardados en contexto para ruta/contacto", flush=True)

    if not search_pool:
        return None, 0.0

    nombre_destino = extraer_nombre_destino(message)
    if nombre_destino:
        nombre_norm = normalizar(nombre_destino)
        coincidencias = [
            item for item in search_pool
            if nombre_norm in normalizar(item.get("nombre", ""))
            or normalizar(item.get("nombre", "")) in nombre_norm
        ]
        if coincidencias:
            search_pool = coincidencias
            print(f">>> Destino resuelto por nombre: {nombre_destino}", flush=True)

    u_lat = u_lon = None
    if location:
        try:
            u_lat, u_lon = map(float, location.split(","))
        except (ValueError, TypeError):
            pass

    def calc_dist(item):
        i_lat, i_lon = item.get("lat"), item.get("lon")
        if u_lat is not None and i_lat is not None and i_lon is not None:
            d_lat = math.radians(i_lat - u_lat)
            d_lon = math.radians(i_lon - u_lon)
            a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(u_lat)) * math.cos(math.radians(i_lat)) * math.sin(d_lon / 2) ** 2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            return 6371 * c
        return 9999

    search_pool.sort(key=calc_dist)
    best = search_pool[0]
    return best, calc_dist(best)

# CURSOR-add: multi-intención → una sola respuesta al usuario
def requiere_respuesta_unificada(intenciones: list) -> bool:
    ignorar = {"SALUDOS"}
    activas = [i for i in intenciones if i not in ignorar]
    return len(activas) > 1

# CURSOR-add: datos concretos de desplazamiento (siempre que haya destino)
def formatear_bloque_ruta_concreto(
    best_business: dict | None,
    distancia_km: float,
    transportistas_sugeridos: list | None = None,
) -> str:
    if not best_business:
        return (
            "No pude trazar la ruta: no hay un vendedor o negocio identificado con coordenadas. "
            "Indica el nombre exacto del destino o repite la búsqueda de producto."
        )
    nombre = best_business.get("nombre", "Destino")
    dist_txt = f"{distancia_km:.1f} km" if distancia_km and distancia_km < 9000 else "distancia por calcular"
    direccion = (
        best_business.get("ubicacion")
        or best_business.get("direccion")
        or best_business.get("address")
        or ""
    )
    telefono = best_business.get("telefono") or best_business.get("contacto") or ""
    lat, lon = best_business.get("lat"), best_business.get("lon")
    lineas = [
        f"Ruta trazada en el mapa hacia {nombre} (~{dist_txt} por carretera, camino más corto disponible).",
        "Sigue la línea azul en el mapa desde tu ubicación actual hasta el marcador de destino.",
    ]
    if direccion:
        lineas.append(f"Dirección de referencia: {direccion}.")
    if telefono:
        lineas.append(f"Teléfono del destino: {telefono}.")
    if lat is not None and lon is not None:
        lineas.append(f"Coordenadas destino: {lat:.5f}, {lon:.5f}.")
    if transportistas_sugeridos:
        lineas.append("Transporte opcional: " + "; ".join(transportistas_sugeridos[:2]) + ".")
    return " ".join(lineas)

# CURSOR-add: resumen factual para síntesis (sin llamar al LLM por intención)
def resumir_contenido_negocio(contenido: list, mercancia: str = "", rol: str = "vendedor") -> str:
    if not contenido:
        return f"No hay {rol}es activos en base para {mercancia or 'la mercancía indicada'}."
    lineas = []
    for item in contenido[:6]:
        trozos = [item.get("nombre", "Sin nombre")]
        if item.get("precio"):
            trozos.append(f"precio {item['precio']}")
        if item.get("mercancia"):
            trozos.append(str(item["mercancia"]))
        ubi = item.get("ubicacion") or item.get("direccion")
        if ubi:
            trozos.append(str(ubi))
        if item.get("telefono"):
            trozos.append(f"tel. {item['telefono']}")
        lineas.append(" | ".join(trozos))
    cabecera = f"Resultados ({rol}, mercancía: {mercancia or 'N/A'}): "
    return cabecera + " /// ".join(lineas)

# CURSOR-add: quitar párrafos y oraciones repetidas
def deduplicar_respuesta(texto: str) -> str:
    if not texto:
        return ""
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    vistos_par = set()
    parrafos_unicos = []
    for p in parrafos:
        clave = normalizar(p)[:160]
        if clave in vistos_par:
            continue
        vistos_par.add(clave)
        oraciones = re.split(r"(?<=[.!?])\s+", p)
        oraciones_unicas = []
        vistos_or = set()
        for o in oraciones:
            o = o.strip()
            if not o:
                continue
            co = normalizar(o)[:100]
            if co in vistos_or:
                continue
            vistos_or.add(co)
            oraciones_unicas.append(o)
        if oraciones_unicas:
            parrafos_unicos.append(" ".join(oraciones_unicas))
    return "\n\n".join(parrafos_unicos).strip()

# CURSOR-add: transportistas/mensajeros activos para ofrecer en la ruta
def obtener_transportistas_disponibles(get_db_func, limit: int = 6) -> list:
    try:
        conn = get_db_func()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_id, nombre, contacto, telefono, correo, ubicacion, lat, lon,
                   comm_status, servicio, tipo
            FROM marketplace
            WHERE LOWER(COALESCE(tipo, '')) IN ('transporte', 'mensajeria', 'mensajero')
               OR LOWER(COALESCE(servicio, '')) LIKE '%transport%'
               OR LOWER(COALESCE(servicio, '')) LIKE '%mensaj%'
            ORDER BY
                CASE WHEN LOWER(COALESCE(comm_status, 'online')) = 'online' THEN 0 ELSE 1 END,
                nombre
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        conn.close()
        cols = [
            "user_id", "nombre", "contacto", "telefono", "correo", "ubicacion",
            "lat", "lon", "comm_status", "servicio", "tipo",
        ]
        resultado = []
        for row in rows:
            item = dict(zip(cols, row))
            status = (item.get("comm_status") or "online").lower()
            item["disponible"] = status in ("online", "away", "")
            item["tipo_servicio"] = (
                "mensajeria"
                if "mensaj" in (item.get("tipo") or "").lower()
                or "mensaj" in (item.get("servicio") or "").lower()
                else "transporte"
            )
            resultado.append(item)
        return [t for t in resultado if t.get("disponible")]
    except Exception as e:
        print(f"⚠️ Error obteniendo transportistas: {e}", flush=True)
        return []

class Orchestrator:
    def __init__(self, context_manager, cola_modelo, get_db_func, worker_url: str, base_prt: str):
        self.context_manager = context_manager
        self.cola_modelo = cola_modelo
        self.get_db = get_db_func
        self.worker_url = worker_url
        self.base_prt = base_prt
        self.intenciones = None

    async def fetch_worker_data(self, user_id: str, message: str, conversation_id: int | None, location: str | None) -> WorkerData:
        payload = {"conversation_id": conversation_id, "message": str(message), "location": location}
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                r = await client.post(f"{self.worker_url}/user/{user_id}/infer", json=payload)
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

    def build_prompt_vars(self, rol: str, datos_db: Dict[str, Any], datos_rag: str, contexto: list, message: str, memoria: list, best_business=None, distancia_km=None) -> Dict[str, Any]:
        rag_limpio = datos_rag[-400:] if datos_rag else "Inicio de conversación limpia."
        memoria_str = "\n".join(memoria) if memoria and isinstance(memoria, list) else ""
        contexto_procesado = contexto[-5:] if contexto else []
        
        return {
            "rol": rol,
            "datos_db": datos_db,
            "datos_rag": rag_limpio,
            "contexto": contexto_procesado,
            "message": message,
            "memoria": memoria_str,

            # 🟩 Variables nuevas para evitar KeyError
            "best_business_name": best_business.get("nombre") if best_business else "",
            "best_business_distance": f"{distancia_km:.1f} km" if distancia_km else "",
            "best_business_lat": best_business.get("lat") if best_business else "",
            "best_business_lon": best_business.get("lon") if best_business else ""
        }

    async def detectar_intencion_remoto(self, mensaje: str, mercancia: str, contexto_previo: str = "") -> str:
        if mensaje:
            payload = {"mensaje": mensaje}
        if contexto_previo:
            payload["contexto"] = contexto_previo
        if mercancia:
            payload["mercancia"] = mercancia
        
        async with httpx.AsyncClient(timeout=2400.0) as client:
            resp = await client.post(
                "http://localhost:9010/infer_intencion",
                json=payload
            )
            data = resp.json()
            intenciones = data.get("intenciones", [])
            if not intenciones:
                intenciones = [data.get("intencion", "OTRA")]
            return intenciones

    # CURSOR-add: una sola llamada LLM que integra todas las intenciones sin repetir
    async def sintetizar_respuesta_unificada(
        self,
        message: str,
        intenciones: list,
        notas: dict,
        mercancia: str,
        contenido_para_prompt: list | dict,
        datos,
        build_prompt_vars_fn,
    ) -> str:
        hechos = []
        for intencion in intenciones:
            if intencion in notas and notas[intencion]:
                hechos.append(f"[{intencion}] {notas[intencion]}")
        hechos_str = "\n".join(hechos) if hechos else "Sin hechos adicionales."

        template_path = Path(f"{self.base_prt}/prompt_multi_intencion.txt")
        if not template_path.exists():
            template_path = Path(f"{self.base_prt}/prompt_tmp/prompt_multi_intencion.txt")
        template = template_path.read_text(encoding="utf-8")
        prompt_cuerpo = (
            template.replace("{intenciones}", ", ".join(intenciones))
            .replace("{message}", message)
            .replace("{mercancia}", mercancia or "N/A")
            .replace("{hechos_intenciones}", hechos_str)
        )

        prompt_reducido = PromptReducerUltra(
            content=contenido_para_prompt if contenido_para_prompt else [],
            contexto_previo=datos.memoria,
            message=message,
            role_broker="multi",
        ).reduce(prompt_cuerpo, intencion=intenciones)

        future = asyncio.get_event_loop().create_future()
        await self.cola_modelo.put((prompt_reducido, future))
        return sanitize_response(await future)

    @staticmethod
    def _publish_sync(topic: str, payload: str):
        """Función síncrona para publicar vía paho-mqtt."""
        publish.single(
            topic=topic,
            payload=payload,
            hostname="127.0.0.1",  # Forzar IPv4
            port=1883,
            qos=1,
            keepalive=300,
        )

    async def registrar_notificacion(self, user_id: str, tipo: str, item: str):
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("UPDATE marketplace SET acepta_notificaciones = 1 WHERE user_id = ?", (user_id,))
        cur.execute("INSERT INTO notificaciones (user_id, tipo, mensaje, estado) VALUES (?, ?, ?, 'pendiente')", (user_id, tipo, f"Esperando coincidencias de {item}"))
        
        # Registrar alerta estructurada para matching automático
        try:
            # Usamos el SQLiteAdapter si está disponible a través del context_manager
            if self.context_manager and hasattr(self.context_manager.db, 'registrar_alerta'):
                self.context_manager.db.registrar_alerta(user_id, tipo, item)
            else:
                # Fallback directo si no está el adapter
                cur.execute("INSERT INTO alerts (user_id, tipo, item, estado) VALUES (?, ?, ?, 'activo')", (user_id, tipo, item))
        except Exception as e:
            print(f"⚠️ Error al registrar alerta estructurada: {e}", flush=True)

        conn.commit()
        conn.close()
        
        try:
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.run_in_executor(
                    executor,
                    self._publish_sync,
                    f"notificaciones/{user_id}",
                    f'{{"tipo":"{tipo}","item":"{item}"}}'
                ),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.warning("Timeout al publicar MQTT (broker lento o no responde)")
        except Exception as e:
            logger.error(f"Error MQTT: {e}")

    async def orchestrate(self, user_id: str, message: str, conversation_id: int | None = None, location: str | None = None) -> Dict[str, Any]:
        contexto_cargado = []
        mercancia_previa = ""
        
        if self.context_manager:
            try:
                contexto_cargado, mercancia_previa = self.context_manager.load_context(user_id)
                print(f"📜 Contexto cargado para {user_id}: {len(contexto_cargado)} líneas", flush=True)
                if mercancia_previa:
                    print(f"📦 Mercancía previa detectada: {mercancia_previa}", flush=True)
            except Exception as e:
                print(f"⚠️ Error cargando contexto: {e}", flush=True)
        
        contexto_str = "\n".join(contexto_cargado) if contexto_cargado else ""
        if mercancia_previa and not contexto_str:
            contexto_str = f"Usuario estaba buscando: {mercancia_previa}"
        elif mercancia_previa and contexto_str:
            contexto_str = f"Búsqueda previa: {mercancia_previa}\n" + contexto_str
        
        datos = await self.fetch_worker_data(user_id, message, conversation_id, location)
        contenido = datos.datos_db.get("content", [])
        mercancia = datos.datos_db.get("mercancia", "")
        
        # Limpieza de mercancia detectada erróneamente (verbos comunes)
        verbos_invalidos = {"podras", "podrás", "puedes", "podrias", "podrías", "puede", "darme", "dame", "pasame", "pásame"}
        if mercancia and mercancia.lower() in verbos_invalidos:
            print(f"⚠️ Mercancía '{mercancia}' detectada como verbo inválido. Ignorando.", flush=True)
            mercancia = ""

        if not mercancia and mercancia_previa:
            if es_nueva_consulta(message):
                print(f"🔄 Nueva consulta detectada. NO reutilizando mercancía previa: {mercancia_previa}", flush=True)
            else:
                mercancia = mercancia_previa
                print(f"♻️ Reutilizando mercancía previa en seguimiento: {mercancia}", flush=True)

        intenciones = await self.detectar_intencion_remoto(message, mercancia, contexto_str)
        print(f"🔍 Intenciones detectadas: {intenciones}", flush=True)

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

        # Limpiar intenciones repetidas y priorizar
        intenciones_limpias = []
        for i in intenciones:
            if i not in intenciones_limpias:
                intenciones_limpias.append(i)
        intenciones = intenciones_limpias

        # Reducción de redundancia: si hay una intención de negocio clara, eliminamos las genéricas
        # que suelen repetir la misma información o causar respuestas redundantes.
        especificas = {"COMPRA", "VENTA", "TRANSPORTE", "SERVICIO", "NEGOCIO", "CONTACTO", "REGISTRO", "MENSAJERIA", "NOTIFICACION"}
        if any(i in especificas for i in intenciones):
            # Filtramos INFORMATIVA, OTRA e INFORMACION si ya hay una específica
            # Mantenemos NOTIFICACION y MOSTRAR_RUTA porque son acciones complementarias legítimas
            intenciones = [i for i in intenciones if i not in {"INFORMATIVA", "OTRA", "INFORMACION", "ACLARAR_INTENCION"}]

        # CURSOR-CHANGE: navegación — multi-intención: añadir/priorizar MOSTRAR_RUTA sin borrar COMPRA, NOTIFICACION, etc.
        if es_solicitud_ruta(message):
            intenciones = [i for i in intenciones if i not in {"CONTACTO", "INFORMATIVA"}]
            if "MOSTRAR_RUTA" not in intenciones:
                intenciones.insert(0, "MOSTRAR_RUTA")
            else:
                intenciones = ["MOSTRAR_RUTA"] + [i for i in intenciones if i != "MOSTRAR_RUTA"]
            print(f">>> Multi-intención con ruta priorizada: {intenciones}", flush=True)

        if ultimo_estado in ["VENTA_SIN_RESULTADOS", "COMPRA_SIN_RESULTADOS", "TRANSPORTE_SIN_RESULTADOS"]:
            if "NOTIFICACION" in intenciones or "CONTACTO" in intenciones:
                for s in ["VENTA", "COMPRA", "TRANSPORTE", "NEGOCIO", "SERVICIO"]:
                    if s in intenciones: intenciones.remove(s)

        print(f"🧹 Intenciones tras limpieza: {intenciones}", flush=True)

        # Capturando las intencioes generales y mantenerla en la clase
        self.intenciones = intenciones

        def build_prompt(nombre_archivo: str) -> str:
            return PromptBuilder(
                Path(f"{self.base_prt}/{nombre_archivo}").read_text(encoding="utf-8"),
                self.build_prompt_vars(
                    datos.rol,
                    datos.datos_db,
                    datos.datos_rag,
                    datos.contexto,
                    message,
                    datos.memoria,
                    best_business=best_business,
                    distancia_km=distancia_km
                )
            ).build()

        def filtrar_contenido(contenido, mercancia):
            if not mercancia:
                return contenido
            merc_norm = normalizar(mercancia)
            return [
                item for item in contenido
                if normalizar(item.get("mercancia", "")) == merc_norm
            ]

        contenido_filtrado = filtrar_contenido(contenido, mercancia)
        
        # --- Pre-cálculo de Ruta y Transportistas ---
        best_business = None
        distancia_km = 0
        transportistas_sugeridos = []

        # CURSOR-CHANGE: resolver destino desde worker o búsqueda previa (segundo turno sin re-inferir COMPRA)
        try:
            best_business, distancia_km = resolver_best_business(
                message,
                location,
                contenido,
                contenido_filtrado,
                self.context_manager,
                user_id,
            )
        except Exception as e:
            print(f"⚠️ Error resolviendo best_business: {e}", flush=True)

        # CURSOR-CHANGE: transportistas estructurados (activos) para UI de ruta
        transportistas_detalle = obtener_transportistas_disponibles(self.get_db, limit=6)
        transportistas_sugeridos = [
            f"{t.get('nombre', 'Transportista')} ({t.get('telefono') or t.get('contacto') or 'sin tel.'})"
            for t in transportistas_detalle
        ]

        respuestas_parciales = []
        estado_final = ultimo_estado
        intenciones_procesadas = set()
        # CURSOR-add: multi-intención → efectos por intención + una sola respuesta sintetizada
        usar_respuesta_unificada = requiere_respuesta_unificada(intenciones)
        notas_para_sintesis: Dict[str, str] = {}
        if usar_respuesta_unificada:
            print(f">>> Modo respuesta unificada para intenciones: {intenciones}", flush=True)

        for intencion in intenciones:
            estado = estado_final
            respuesta = ""
            
            if (estado or contexto_cargado) and intencion in {"INFORMATIVA", "OTRA"}:
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
                if estado and estado in estado_a_intencion:
                    nueva_int = estado_a_intencion[estado]
                    if nueva_int not in intenciones:
                        print(f">>> Reutilizando intención previa (desde estado): {nueva_int}", flush=True)
                        intencion = nueva_int
                    else:
                        print(f">>> Saltando remapeo por estado: {nueva_int} ya está en la lista", flush=True)
                elif contexto_cargado and mercancia_previa:
                    if "COMPRA" not in intenciones:
                        print(f">>> Detectando intención por contexto (mercancía previa): COMPRA", flush=True)
                        intencion = "COMPRA"
                    else:
                        print(f">>> Saltando remapeo por contexto: COMPRA ya está en la lista", flush=True)

            if intencion in intenciones_procesadas:
                print(f">>> Saltando intención ya procesada: {intencion}", flush=True)
                continue
            
            intenciones_procesadas.add(intencion)

            # ------------------ COMPRA ------------------
            if intencion == "COMPRA":
                if usar_respuesta_unificada:
                    if not contenido_filtrado:
                        notas_para_sintesis["COMPRA"] = "No hay vendedores activos para la mercancía solicitada."
                        estado = "COMPRA_SIN_RESULTADOS"
                    else:
                        if self.context_manager:
                            self.context_manager.store_search_results(user_id, contenido_filtrado, mercancia)
                        notas_para_sintesis["COMPRA"] = resumir_contenido_negocio(
                            contenido_filtrado, mercancia, "vendedor"
                        )
                        estado = "COMPRA"
                    estado_final = estado
                    continue

                if not contenido_filtrado:
                    if "NOTIFICACION" in intenciones or "CONTACTO" in intenciones:
                        respuesta = "No hay vendedores activos para la mercancía solicitada."
                    else:
                        respuesta = (
                            "No hay vendedores activos para la mercancía solicitada.\n"
                            "Puedes registrarte como comprador y te avisaré cuando aparezcan vendedores."
                        )
                    estado = "COMPRA_SIN_RESULTADOS"
                else:
                    if self.context_manager:
                        self.context_manager.store_search_results(user_id, contenido_filtrado, mercancia)
                    
                    prompt_base = "broker_prompt_vendedor.txt"
                    prompt_completo = build_prompt(prompt_base)
                    prompt_reducido = PromptReducerUltra(
                        content=contenido_filtrado,
                        contexto_previo = datos.memoria,
                        message=message,
                        role_broker="vendedor",
                    ).reduce(prompt_completo, intencion=self.intenciones)
                    
                    future = asyncio.get_event_loop().create_future()
                    await self.cola_modelo.put((prompt_reducido, future))
                    respuesta = sanitize_response(await future)
                    estado = "COMPRA"

            # ------------------ VENTA ------------------
            elif intencion == "VENTA":
                if usar_respuesta_unificada:
                    if not contenido_filtrado:
                        notas_para_sintesis["VENTA"] = "No hay compradores activos para el producto."
                        estado = "VENTA_SIN_RESULTADOS"
                    else:
                        if self.context_manager:
                            self.context_manager.store_search_results(user_id, contenido_filtrado, mercancia)
                        notas_para_sintesis["VENTA"] = resumir_contenido_negocio(
                            contenido_filtrado, mercancia, "comprador"
                        )
                        estado = "VENTA"
                    estado_final = estado
                    continue

                if not contenido_filtrado:
                    if "NOTIFICACION" in intenciones or "CONTACTO" in intenciones:
                        respuesta = "No hay compradores activos para tu producto."
                    else:
                        respuesta = (
                            "No hay compradores activos para tu producto.\n"
                            "Puedes registrarte como vendedor y te avisaré cuando aparezcan interesados."
                        )
                    estado = "VENTA_SIN_RESULTADOS"
                else:
                    if self.context_manager:
                        self.context_manager.store_search_results(user_id, contenido_filtrado, mercancia)
                    
                    prompt_base = "broker_prompt_comprador.txt"
                    prompt_completo = build_prompt(prompt_base)
                    prompt_reducido = PromptReducerUltra(
                        content=contenido_filtrado,
                        contexto_previo = datos.memoria,
                        message=message,
                        role_broker="comprador",
                    ).reduce(prompt_completo, intencion=self.intenciones)
                    
                    future = asyncio.get_event_loop().create_future()
                    await self.cola_modelo.put((prompt_reducido, future))
                    respuesta = sanitize_response(await future)
                    estado = "VENTA"

            # ------------------ TRANSPORTE ------------------
            elif intencion == "TRANSPORTE":
                if usar_respuesta_unificada:
                    notas_para_sintesis["TRANSPORTE"] = (
                        resumir_contenido_negocio(contenido_filtrado, mercancia, "transporte")
                        if contenido_filtrado
                        else "Sin transportistas coincidentes en base."
                    )
                    estado = "TRANSPORTE"
                    estado_final = estado
                    continue

                prompt_base = "prompt_transporte.txt"
                prompt_completo = build_prompt(prompt_base)
                prompt_reducido = PromptReducerUltra(
                    content=contenido_filtrado,
                    contexto_previo = datos.memoria,
                    message=message,
                    role_broker="transporte",
                ).reduce(prompt_completo, intencion=self.intenciones)
                    
                future = asyncio.get_event_loop().create_future()
                await self.cola_modelo.put((prompt_reducido, future))
                respuesta = sanitize_response(await future)
                estado = "TRANSPORTE"

            # ------------------ SERVICIO ------------------
            elif intencion == "SERVICIO":
                if usar_respuesta_unificada:
                    notas_para_sintesis["SERVICIO"] = (
                        resumir_contenido_negocio(contenido_filtrado, mercancia, "servicio")
                        if contenido_filtrado
                        else "Sin servicios coincidentes en base."
                    )
                    estado = "SERVICIO"
                    estado_final = estado
                    continue

                prompt_completo = build_prompt("prompt_servicio.txt")
                prompt_reducido = PromptReducerUltra(
                    content=contenido_filtrado,
                    contexto_previo = datos.memoria,
                    message=message,
                    role_broker="servicio",
                ).reduce(prompt_completo, intencion=self.intenciones)
                    
                future = asyncio.get_event_loop().create_future()
                await self.cola_modelo.put((prompt_reducido, future))
                respuesta = sanitize_response(await future)
                estado = "SERVICIO"

            # ------------------ INFORMACIÓN ------------------
            elif intencion == "INFORMACION" or intencion == "INFORMATIVA":
                if usar_respuesta_unificada:
                    notas_para_sintesis[intencion] = (
                        resumir_contenido_negocio(contenido_filtrado, mercancia, "info")
                        if contenido_filtrado
                        else "Consulta informativa sin catálogo adicional en este turno."
                    )
                    estado = "INFORMACION"
                    estado_final = estado
                    continue

                prompt_completo = build_prompt("prompt_informativo.txt")
                prompt_reducido = PromptReducerUltra(
                    content=contenido_filtrado,
                    contexto_previo = datos.memoria,
                    message=message,
                    role_broker="informativa",
                ).reduce(prompt_completo, intencion=self.intenciones)
                    
                future = asyncio.get_event_loop().create_future()
                await self.cola_modelo.put((prompt_reducido, future))
                respuesta = sanitize_response(await future)
                estado = "INFORMACION"

            # ------------------ NEGOCIO ------------------
            elif intencion == "NEGOCIO":
                if usar_respuesta_unificada:
                    notas_para_sintesis["NEGOCIO"] = resumir_contenido_negocio(
                        contenido_filtrado, mercancia, "negocio"
                    )
                    estado = "NEGOCIO"
                    estado_final = estado
                    continue

                prompt_completo = build_prompt("prompt_negocio.txt")
                prompt_reducido = PromptReducerUltra(
                    content=contenido_filtrado,
                    contexto_previo = datos.memoria,
                    message=message,
                    role_broker="negocio",
                ).reduce(prompt_completo, intencion=self.intenciones)
                    
                future = asyncio.get_event_loop().create_future()
                await self.cola_modelo.put((prompt_reducido, future))
                respuesta = sanitize_response(await future)
                estado = "NEGOCIO"

            # ------------------ CONTACTO ------------------
            elif intencion == "CONTACTO":
                if usar_respuesta_unificada:
                    stored_results = None
                    if self.context_manager:
                        stored_results = self.context_manager.get_search_results(user_id)
                    pool = (
                        (stored_results or {}).get("contenido")
                        or contenido_filtrado
                        or []
                    )
                    notas_para_sintesis["CONTACTO"] = resumir_contenido_negocio(
                        pool, (stored_results or {}).get("mercancia", mercancia), "contacto"
                    )
                    estado = "CONTACTO"
                    estado_final = estado
                    continue

                stored_results = None
                if self.context_manager:
                    stored_results = self.context_manager.get_search_results(user_id)
                
                if stored_results and stored_results.get("contenido"):
                    contenido_para_contacto = stored_results.get("contenido", [])
                    mercancia_contacto = stored_results.get("mercancia", "")
                    
                    es_vendedor = any(
                        item.get("Tipo", "").lower() == "vendedor" for item in contenido_para_contacto
                    )
                    
                    prompt_base = "broker_prompt_vendedor.txt" if es_vendedor else "broker_prompt_comprador.txt"
                    
                    prompt_completo = build_prompt(prompt_base)
                    prompt_reducido = PromptReducerUltra(
                        content=contenido_para_contacto,
                        contexto_previo=datos.memoria,
                        message=message,
                        role_broker="vendedor" if es_vendedor else "comprador",
                    ).reduce(prompt_completo, intencion=self.intenciones)
                    
                    future = asyncio.get_event_loop().create_future()
                    await self.cola_modelo.put((prompt_reducido, future))
                    respuesta = sanitize_response(await future)
                else:
                    prompt_completo = build_prompt("prompt_contacto.txt")
                    prompt_reducido = PromptReducerUltra(
                        content=contenido_filtrado,
                        contexto_previo = datos.memoria,
                        message=message,
                        role_broker="contacto",
                    ).reduce(prompt_completo, intencion=self.intenciones)
                    
                    future = asyncio.get_event_loop().create_future()
                    await self.cola_modelo.put((prompt_reducido, future))
                    respuesta = sanitize_response(await future)
                
                estado = "CONTACTO"

            # ------------------ MENSAJERÍA ------------------
            elif intencion == "MENSAJERIA":
                if usar_respuesta_unificada:
                    notas_para_sintesis["MENSAJERIA"] = (
                        "El usuario consulta envío/entrega/mensajería para la mercancía en contexto."
                    )
                    estado = "MENSAJERIA"
                    estado_final = estado
                    continue

                prompt_completo = build_prompt("prompt_mensajeria.txt")
                prompt_reducido = PromptReducerUltra(
                    content=contenido_filtrado,
                    contexto_previo = datos.memoria,
                    message=message,
                    role_broker="mensajeria",
                ).reduce(prompt_completo, intencion=self.intenciones)
                    
                future = asyncio.get_event_loop().create_future()
                await self.cola_modelo.put((prompt_reducido, future))
                respuesta = sanitize_response(await future)
                estado = "MENSAJERIA"

            # ------------------ NOTIFICACIÓN ------------------
            elif intencion == "NOTIFICACION":
                if usar_respuesta_unificada:
                    if estado == "COMPRA_SIN_RESULTADOS":
                        await self.registrar_notificacion(user_id, "COMPRA", mercancia)
                        notas_para_sintesis["NOTIFICACION"] = (
                            "Alerta de compra registrada: avisaré cuando aparezcan vendedores."
                        )
                        estado = "ESPERA_NOTIFICACION_COMPRA"
                    elif estado == "VENTA_SIN_RESULTADOS":
                        await self.registrar_notificacion(user_id, "VENTA", mercancia)
                        notas_para_sintesis["NOTIFICACION"] = (
                            "Alerta de venta registrada: avisaré cuando aparezcan compradores."
                        )
                        estado = "ESPERA_NOTIFICACION_VENTA"
                    elif estado == "TRANSPORTE_SIN_RESULTADOS":
                        await self.registrar_notificacion(user_id, "TRANSPORTE", mercancia or message)
                        notas_para_sintesis["NOTIFICACION"] = (
                            "Alerta de transporte registrada."
                        )
                        estado = "ESPERA_NOTIFICACION_TRANSPORTE"
                    else:
                        notas_para_sintesis["NOTIFICACION"] = (
                            "El usuario pidió ser notificado; confirmar si aplica a la búsqueda actual."
                        )
                        estado = "NOTIFICACION_INVALIDA"
                    estado_final = estado
                    continue

                if "CONTACTO" in intenciones:
                    respuesta_base = ""
                else:
                    prompt_completo = build_prompt("prompt_notificacion.txt")
                    prompt_reducido = PromptReducerUltra(
                        content=contenido_filtrado,
                        contexto_previo = datos.memoria,
                        message=message,
                        role_broker="notificacion",
                    ).reduce(prompt_completo, intencion=self.intenciones)
                        
                    future = asyncio.get_event_loop().create_future()
                    await self.cola_modelo.put((prompt_reducido, future))
                    respuesta_base = sanitize_response(await future)

                if estado == "COMPRA_SIN_RESULTADOS":
                    await self.registrar_notificacion(user_id, "COMPRA", mercancia)
                    if not respuesta_base:
                        respuesta = ""
                    else:
                        respuesta = f"{respuesta_base}\nPerfecto, te avisaré cuando aparezcan vendedores."
                    estado = "ESPERA_NOTIFICACION_COMPRA"

                elif estado == "VENTA_SIN_RESULTADOS":
                    await self.registrar_notificacion(user_id, "VENTA", mercancia)
                    if not respuesta_base:
                        respuesta = ""
                    else:
                        respuesta = f"{respuesta_base}\nPerfecto, te avisaré cuando aparezcan compradores."
                    estado = "ESPERA_NOTIFICACION_VENTA"

                elif estado == "TRANSPORTE_SIN_RESULTADOS":
                    await self.registrar_notificacion(user_id, "TRANSPORTE", mercancia or message)
                    if not respuesta_base:
                        respuesta = ""
                    else:
                        respuesta = f"{respuesta_base}\nPerfecto, te avisaré cuando aparezcan opciones de transporte."
                    estado = "ESPERA_NOTIFICACION_TRANSPORTE"

                else:
                    if not respuesta_base:
                        respuesta = ""
                    else:
                        respuesta = f"{respuesta_base}\nNo tengo pendiente ninguna notificación para activar."
                    estado = "NOTIFICACION_INVALIDA"

            # ------------------ ACLARAR INTENCIÓN ------------------
            elif intencion == "ACLARAR_INTENCION":
                if usar_respuesta_unificada:
                    notas_para_sintesis["ACLARAR_INTENCION"] = (
                        "La intención no es totalmente clara; pedir aclaración breve si hace falta."
                    )
                    estado = "ACLARAR_INTENCION"
                    estado_final = estado
                    continue

                if contenido_filtrado and mercancia:
                    tipos = {item.get("Tipo", "").lower() for item in contenido_filtrado}
                    if "vendedor" in tipos:
                        intencion = "COMPRA"
                    elif "comprador" in tipos:
                        intencion = "VENTA"

                if intencion == "COMPRA":
                    prompt_base = "broker_prompt_vendedor.txt"
                    prompt_completo = build_prompt(prompt_base)
                    prompt_reducido = PromptReducerUltra(
                        content=contenido_filtrado,
                        contexto_previo = datos.memoria,
                        message=message,
                        role_broker="vendedor",
                    ).reduce(prompt_completo, intencion=self.intenciones)
                    
                    future = asyncio.get_event_loop().create_future()
                    await self.cola_modelo.put((prompt_reducido, future))
                    respuesta = sanitize_response(await future)
                    estado = "COMPRA"

                elif intencion == "VENTA":
                    prompt_base = "broker_prompt_comprador.txt"
                    prompt_completo = build_prompt(prompt_base)
                    prompt_reducido = PromptReducerUltra(
                        content=contenido_filtrado,
                        contexto_previo = datos.memoria,
                        message=message,
                        role_broker="comprador",
                    ).reduce(prompt_completo, intencion=self.intenciones)
                    
                    future = asyncio.get_event_loop().create_future()
                    await self.cola_modelo.put((prompt_reducido, future))
                    respuesta = sanitize_response(await future)
                    estado = "VENTA"

                else:
                    system_block = (
                        "La intención detectada no es clara. Formula una pregunta breve y directa para aclarar si el usuario quiere "
                        "COMPRAR o VENDER."
                    )
                    prompt_final = (
                        f"{system_block}\n\n<<USR>>\n{message}\n<<END_USR>>"
                    )
                    
                    future = asyncio.get_event_loop().create_future()
                    await self.cola_modelo.put((prompt_final, future))
                    respuesta = sanitize_response(await future)
                    estado = "ACLARAR_INTENCION"

            # ------------------ REGISTRO ------------------
            elif intencion == "REGISTRO":
                if usar_respuesta_unificada:
                    notas_para_sintesis["REGISTRO"] = "El usuario desea registrarse o completar alta en la plataforma."
                    estado = "REGISTRO"
                    estado_final = estado
                    continue

                prompt_base = "prompt_registro.txt"
                prompt_completo = build_prompt(prompt_base)
                prompt_reducido = PromptReducerUltra(
                    content=contenido_filtrado,
                    contexto_previo=datos.memoria,
                    message=message,
                    role_broker="registro",
                ).reduce(prompt_completo, intencion=self.intenciones)

                future = asyncio.get_event_loop().create_future()
                await self.cola_modelo.put((prompt_reducido, future))
                respuesta = sanitize_response(await future)
                estado = "REGISTRO"

            # ------------------ MOSTRAR RUTA ------------------
            elif intencion == "MOSTRAR_RUTA":
                if usar_respuesta_unificada:
                    notas_para_sintesis["MOSTRAR_RUTA"] = formatear_bloque_ruta_concreto(
                        best_business, distancia_km, transportistas_sugeridos
                    )
                    estado = "MOSTRAR_RUTA"
                    estado_final = estado
                    continue

                prompt_base = "prompt_ruta.txt"
                prompt_completo = build_prompt(prompt_base)
                
                # Preparamos el contenido para el broker de ruta
                ruta_content = {
                    "best_business_name": best_business.get("nombre", "el destino") if best_business else "el destino",
                    "distancia_km": f"{distancia_km:.2f}" if best_business else "desconocida",
                    "transportistas": transportistas_sugeridos
                }
                
                prompt_reducido = PromptReducerUltra(
                    content=ruta_content,
                    contexto_previo = datos.memoria,
                    message=message,
                    role_broker="ruta",
                ).reduce(prompt_completo, intencion=self.intenciones)

                future = asyncio.get_event_loop().create_future()
                await self.cola_modelo.put((prompt_reducido, future))
                respuesta = sanitize_response(await future)
                # CURSOR-CHANGE: mono-intención ruta — datos concretos + texto LLM sin duplicar
                bloque_ruta = formatear_bloque_ruta_concreto(
                    best_business, distancia_km, transportistas_sugeridos
                )
                respuesta = deduplicar_respuesta(f"{bloque_ruta}\n\n{respuesta}".strip())
                estado = "MOSTRAR_RUTA"

            # ------------------ OTRA ------------------
            else:
                if usar_respuesta_unificada:
                    notas_para_sintesis[intencion] = "Solicitud general; responder con cortesía y pedir aclaración si falta datos."
                    estado = "OTRA"
                    estado_final = estado
                    continue

                prompt_completo = build_prompt("prompt_otra.txt")
                prompt_reducido = PromptReducerUltra(
                    content=contenido_filtrado,
                    contexto_previo = datos.memoria,
                    message=message,
                    role_broker="otra",
                ).reduce(prompt_completo, intencion=self.intenciones)
                    
                future = asyncio.get_event_loop().create_future()
                await self.cola_modelo.put((prompt_reducido, future))
                respuesta = sanitize_response(await future)
                estado = "OTRA"
            
            if usar_respuesta_unificada:
                if intencion not in notas_para_sintesis:
                    notas_para_sintesis[intencion] = (
                        (respuesta[:800] if respuesta else f"Intención {intencion} detectada.")
                    )
                if intencion in especificas or intencion == "MOSTRAR_RUTA":
                    estado_final = estado
                continue

            if respuesta and not usar_respuesta_unificada:
                respuestas_parciales.append(respuesta)
                if intencion in especificas or intencion == "MOSTRAR_RUTA":
                    estado_final = estado
                if isinstance(datos.memoria, list):
                    datos.memoria.append(f"IA (Turno Actual): {respuesta}")

        # CURSOR-CHANGE: respuesta única coherente en multi-intención
        if usar_respuesta_unificada:
            if es_solicitud_ruta(message) or "MOSTRAR_RUTA" in intenciones:
                notas_para_sintesis["MOSTRAR_RUTA"] = formatear_bloque_ruta_concreto(
                    best_business, distancia_km, transportistas_sugeridos
                )
            contenido_prompt = contenido_filtrado or contenido
            if self.context_manager:
                stored = self.context_manager.get_search_results(user_id)
                if stored and stored.get("contenido"):
                    contenido_prompt = stored["contenido"]
            cuerpo = await self.sintetizar_respuesta_unificada(
                message,
                intenciones,
                notas_para_sintesis,
                mercancia,
                contenido_prompt,
                datos,
                None,
            )
            bloque_ruta = notas_para_sintesis.get("MOSTRAR_RUTA", "")
            if bloque_ruta:
                respuesta_final = deduplicar_respuesta(f"{bloque_ruta}\n\n{cuerpo}".strip())
            else:
                respuesta_final = deduplicar_respuesta(cuerpo)
        else:
            respuesta_final = deduplicar_respuesta("\n\n".join(respuestas_parciales))

        # CURSOR-add: si pidió ruta en mono-intención sin pasar por bloque MOSTRAR_RUTA
        if (
            not usar_respuesta_unificada
            and (es_solicitud_ruta(message) or "MOSTRAR_RUTA" in intenciones)
            and best_business
            and "Ruta trazada en el mapa" not in respuesta_final
        ):
            bloque = formatear_bloque_ruta_concreto(
                best_business, distancia_km, transportistas_sugeridos
            )
            respuesta_final = deduplicar_respuesta(f"{bloque}\n\n{respuesta_final}".strip())

        if self.context_manager:
            try:
                self.context_manager.save_context(
                    user_id=user_id,
                    user_msg=f"USUARIO: {message}",
                    ai_msg=f"IA: {respuesta_final}",
                    current_product_query=mercancia,
                    tipo=datos.rol
                )
                print(f"✅ Contexto guardado para user {user_id}: {message[:50]}...", flush=True)
            except Exception as e:
                print(f"⚠️ Error al guardar contexto: {e}", flush=True)

        # Determinar acción final
        action = None
        payload = {"mercancia": mercancia}

        # CURSOR-CHANGE: ROUTE tiene prioridad sobre CONNECT en preguntas de navegación
        dest_lat = best_business.get("lat") if best_business else None
        dest_lon = best_business.get("lon") if best_business else None
        if (
            best_business
            and dest_lat is not None
            and dest_lon is not None
            and ("MOSTRAR_RUTA" in intenciones or es_solicitud_ruta(message))
        ):
            action = "ROUTE"
            payload["dest"] = {
                "lat": dest_lat,
                "lng": dest_lon,
                "name": best_business.get("nombre", "Destino"),
                # CURSOR-add: datos concretos para UI / desplazamiento
                "distance_km": round(distancia_km, 1) if distancia_km and distancia_km < 9000 else None,
                "address": (
                    best_business.get("ubicacion")
                    or best_business.get("direccion")
                    or best_business.get("address")
                ),
                "phone": best_business.get("telefono") or best_business.get("contacto"),
            }
            payload["transportistas"] = [
                {
                    "user_id": t.get("user_id"),
                    "name": t.get("nombre"),
                    "phone": t.get("telefono") or t.get("contacto"),
                    "email": t.get("correo"),
                    "address": t.get("ubicacion"),
                    "status": t.get("comm_status") or "online",
                    "service_type": t.get("tipo_servicio", "transporte"),
                    "available": t.get("disponible", True),
                }
                for t in transportistas_detalle
            ]
            print(f">>> Acción ROUTE hacia {payload['dest']['name']} ({dest_lat}, {dest_lon})", flush=True)
        elif "CONTACTO" in intenciones and best_business and not es_solicitud_ruta(message):
            # Si el usuario pide contacto, verificamos si quiere un medio específico
            comm_type = "chat"
            if "whatsapp" in message.lower(): comm_type = "whatsapp"
            elif "correo" in message.lower() or "email" in message.lower(): comm_type = "email"
            
            # Obtener info extendida del vendedor
            comm_info = {"status": "offline", "social_links": {}}
            try:
                conn = self.get_db()
                cur = conn.cursor()
                cur.execute("SELECT comm_status, social_links FROM marketplace WHERE user_id = ?", (best_business.get("user_id"),))
                row = cur.fetchone()
                if row:
                    comm_info = {
                        "status": row[0] or "offline",
                        "social_links": json.loads(row[1]) if row[1] else {}
                    }
                conn.close()
            except: pass

            # Determinar si el usuario dio una orden directa de preguntar/comunicar
            auto_ask = False
            question_to_ask = ""
            for verb in ["preguntale", "pregúntale", "dile", "consulta", "avísale"]:
                if verb in message.lower():
                    auto_ask = True
                    # Extraer lo que hay que preguntar (aproximado)
                    parts = re.split(rf"\b{verb}\b", message.lower(), maxsplit=1)
                    if len(parts) > 1:
                        question_to_ask = parts[1].strip()
                    break

            action = "CONNECT"
            if auto_ask and best_business:
                action = "AUTO_ASK"
                # Intentar enviar el mensaje automáticamente a través de comm_service (puerto 9005)
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        await client.post("http://localhost:9005/send", json={
                            "sender_id": user_id,
                            "receiver_id": best_business.get("user_id"),
                            "text": f"[Vainilla AI]: El usuario pregunta: {question_to_ask}",
                            "type": "chat"
                        })
                except Exception as e:
                    print(f"⚠️ Error en envío automático: {e}")

            payload["conn"] = {
                "type": comm_type,
                "auto_ask": auto_ask,
                "question": question_to_ask,
                "user_id": best_business.get("user_id"),
                "name": best_business.get("nombre"),
                "phone": best_business.get("telefono"),
                "email": best_business.get("correo"),
                "status": comm_info["status"],
                "social_links": comm_info["social_links"]
            }
        elif mercancia and (estado_final in ["COMPRA", "VENTA", "NEGOCIO", "SERVICIO"]):
            action = "FILTER_MAP"

        return {
            "response": respuesta_final,
            "action": action,
            "payload": payload
        }
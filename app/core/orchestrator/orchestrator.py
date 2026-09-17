"""
HellenCommerce 2.0.1 - Orchestrator Core

Orquestador central como librería interna (NO microservicio).
Coordina todo el flujo de peticiones desde FastAPI hacia los microservicios especializados.

Flujo:
1. Recibe petición desde FastAPI WebSocket
2. Detecta intención(es) vía intent_service
3. Genera prompts personalizados vía worker_service  
4. Despacha en paralelo a servicios especializados (fan-out)
5. Unifica respuestas vía mistral_service
6. Persiste contexto en SQLite/ChromaDB/Qdrant
7. Retorna respuesta al cliente vía WebSocket
"""

import asyncio
import json
import os
import sys
import re
import unicodedata
import httpx
import platform
import websockets
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.orchestrator.intent_detector import IntentDetector
from app.core.orchestrator.prompt_builder import PromptBuilderService
from app.core.orchestrator.specialized_dispatcher import SpecializedDispatcher
from app.core.orchestrator.response_unifier import ResponseUnifier
from app.core.orchestrator.logging_client import LoggingClient


@dataclass
class OrchestrationContext:
    """Contexto de orquestación para cada petición."""
    user_id: str
    message: str
    conversation_id: Optional[int] = None
    location: Optional[str] = None
    intents: List[str] = None
    prompts: Dict[str, str] = None
    partial_responses: List[Dict[str, Any]] = None
    final_response: str = ""
    start_time: datetime = None
    
    def __post_init__(self):
        if self.intents is None:
            self.intents = []
        if self.prompts is None:
            self.prompts = {}
        if self.partial_responses is None:
            self.partial_responses = []
        if self.start_time is None:
            self.start_time = datetime.utcnow()


class Orchestrator:
    """
    Orquestador central como librería interna.
    Coordina la comunicación entre FastAPI y todos los microservicios especializados.
    """

    @staticmethod
    def _normalize_service_url(url: Optional[str], service_name: str, scheme: str = "http") -> str:
        """Normaliza URLs viejas a los nombres reales de Docker con prefijo bunker, respetando túneles externos."""
        if not url:
            return f"{scheme}://bunker_{service_name}"

        value = url.strip()

        # 1. PASO EXPRÉS: Si es un túnel público de Cloudflare u otros, NO TOCAR.
        external_tunnel_indicators = ["trycloudflare.com", "ngrok-free.app", "ngrok.io", "localhost.run"]
        if any(indicator in value for indicator in external_tunnel_indicators):
            return value

        legacy_aliases = {
            "http://127.0.0.1:9010": "http://bunker_intent_service:9010",
            "http://intent_service:9010": "http://bunker_intent_service:9010",
            "https://127.0.0.1:9010": "http://bunker_intent_service:9010",
            "ws://127.0.0.1:8099/ws/logs": "ws://bunker_logging_service:8099/ws/logs",
            "ws://logging_service:8099/ws/logs": "ws://bunker_logging_service:8099/ws/logs",
            "http://bunker_intent_service:9010": "http://bunker_intent_service:9010",
            "http://bunker_worker_service:9000": "http://bunker_worker_service:9000",
            "http://bunker_mistral_service:9001": "http://bunker_mistral_service:9001",
            "ws://bunker_logging_service:8099/ws/logs": "ws://bunker_logging_service:8099/ws/logs",
        }

        if value in legacy_aliases:
            return legacy_aliases[value]

        if value.startswith("http://localhost") or value.startswith("https://localhost"):
            return f"{scheme}://bunker_{service_name}"

        if value.startswith("http://127.0.0.1") or value.startswith("https://127.0.0.1"):
            return value.replace("127.0.0.1", f"bunker_{service_name}").replace("https://", f"{scheme}://").replace("http://", f"{scheme}://")

        if value.startswith(f"{scheme}://"):
            host = value.split("//", 1)[1].split("/", 1)[0]
            if host in {service_name, f"bunker_{service_name}"}:
                return f"{scheme}://bunker_{service_name}" + ("" if value.split("//", 1)[1].split("/", 1)[1:] == [] else "/" + value.split("//", 1)[1].split("/", 1)[1])
            if host.startswith("bunker_"):
                return value
            return value.replace(host, f"bunker_{service_name}")

        # Retornado a tu lógica original exacta para ws://
        if value.startswith("ws://"):
            host = value.split("//", 1)[1].split("/", 1)[0]
            if host in {service_name, f"bunker_{service_name}"}:
                return f"ws://bunker_{service_name}" + ("" if value.split("//", 1)[1].split("/", 1)[1:] == [] else "/" + value.split("//", 1)[1].split("/", 1)[1])
            if host.startswith("bunker_"):
                return value
            return value.replace(host, f"bunker_{service_name}")

        return value

        # Error: no se pudo conectar al WS wss://effect-approval-advances-lecture.trycloudflare.com/ws/cX6ApEM1JiQAOjUXVVWjV3NWAaW2: websocket: bad handshake
    
    def __init__(
        self,
        context_manager=None,
        get_db_func=None,
        base_prompts_path: str = None,
        base_resources_path: str = None
    ):
        self.context_manager = context_manager
        self.get_db = get_db_func

        system = platform.system()    
        from app.utils.paths import hc_path
        self.base_prompts_path = base_prompts_path or hc_path("app/prompts")
        self.base_resources_path = base_resources_path or hc_path("app/resources")
        
        # URLs de microservicios (configurables vía environment), normalizadas para Docker
        self.intent_service_url = self._normalize_service_url(os.getenv("INTENT_SERVICE_URL"), "intent_service", "http")
        self.worker_service_url = self._normalize_service_url(os.getenv("WORKER_SERVICE_URL"), "worker_service", "http")
        self.mistral_service_url = self._normalize_service_url(os.getenv("MISTRAL_SERVICE_URL"), "mistral_service", "http")
        self.logging_ws_url = self._normalize_service_url(os.getenv("LOGGING_WS_URL"), "logging_service", "ws")
        
        # URLs de servicios especializados (fan-out)
        self.specialized_services = {
            "REGISTRO": self._normalize_service_url(os.getenv("REGISTRO_SERVICE_URL"), "registro_service", "http"),
            "CONTACTO": self._normalize_service_url(os.getenv("CONTACTO_SERVICE_URL"), "contacto_service", "http"),
            "MENSAJERIA": self._normalize_service_url(os.getenv("MENSAJERIA_SERVICE_URL"), "mensajeria_service", "http"),
            "VENTA": self._normalize_service_url(os.getenv("VENTA_SERVICE_URL"), "venta_service", "http"),
            "COMPRA": self._normalize_service_url(os.getenv("COMPRA_SERVICE_URL"), "compra_service", "http"),
            "INFORMATIVA": self._normalize_service_url(os.getenv("INFORMATIVA_SERVICE_URL"), "informativa_service", "http"),
            "NOTIFICACION": self._normalize_service_url(os.getenv("NOTIFICACION_SERVICE_URL"), "notificacion_service", "http"),
            "TRANSPORTE": self._normalize_service_url(os.getenv("TRANSPORTE_SERVICE_URL"), "transporte_service", "http"),
            "SALUDO": self._normalize_service_url(os.getenv("SALUDO_SERVICE_URL"), "saludo_service", "http"),
            "DESPEDIDA": self._normalize_service_url(os.getenv("DESPEDIDA_SERVICE_URL"), "despedida_service", "http"),
            "RUTA": self._normalize_service_url(os.getenv("RUTA_SERVICE_URL"), "ruta_service", "http"),
            "NEGOCIO": self._normalize_service_url(os.getenv("NEGOCIO_SERVICE_URL"), "negocio_service", "http"),
            "SERVICIO": self._normalize_service_url(os.getenv("SERVICIO_SERVICE_URL"), "servicio_service", "http"),
            "OTRA": self._normalize_service_url(os.getenv("OTRA_SERVICE_URL"), "otra_service", "http")
        }
        
        # Componentes del orquestador
        self.intent_detector = IntentDetector(self.intent_service_url)
        self.prompt_builder = PromptBuilderService(self.worker_service_url, self.base_prompts_path)
        self.dispatcher = SpecializedDispatcher(self.specialized_services)
        self.response_unifier = ResponseUnifier(self.mistral_service_url)
        self.logging_client = LoggingClient(self.logging_ws_url)
        
        # Cola para procesamiento asíncrono de respuestas del modelo
        self.model_queue = asyncio.Queue()
        
        print("✅ Orchestrator inicializado como librería interna", flush=True)
    
    async def log_event(self, level: str, message: str, source_file: str = "orchestrator.py", line_number: int = 0):
        """Envía log al subsistema de logging."""
        try:
            await self.logging_client.send_log(
                level=level,
                service_origin="orchestrator",
                source_file=source_file,
                line_number=line_number,
                message=message
            )
        except Exception as e:
            print(f"⚠️ Error enviando log: {e}", flush=True)
    
    async def orchestrate(
        self,
        user_id: str,
        message: str,
        conversation_id: Optional[int] = None,
        location: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Método principal de orquestación. Coordina todo el flujo de procesamiento.
        
        Args:
            user_id: Identificador (único) del usuario
            message: Mensaje del usuario
            conversation_id: ID de la conversación actual (opcional)
            location: Ubicación del usuario en formato "lat,lon" (opcional)
            
        Returns:
            Diccionario con la respuesta final para el cliente
        """
        ctx = OrchestrationContext(
            user_id=user_id,
            message=message,
            conversation_id=conversation_id,
            location=location
        )
        
        try:
            await self.log_event("INFO", f"Iniciando orquestación para usuario {user_id}", line_number=97)
            print(f"🟢 Orquestación iniciada para usuario {user_id}", flush=True)

            # 1. Cargar contexto previo
            contexto_previo = []
            mercancia_previa = ""
            if self.context_manager:
                try:
                    contexto_previo, mercancia_previa = self.context_manager.load_context(user_id)
                    await self.log_event("INFO", f"Contexto cargado: {len(contexto_previo)} líneas, mercancía: {mercancia_previa}", line_number=107)
                    print(f"Contexto cargado: {len(contexto_previo)} líneas, mercancía: {mercancia_previa}", flush=True)
                except Exception as e:
                    await self.log_event("WARNING", f"Error cargando contexto: {e}", line_number=109)
            
            # 2. Detectar intención(es) 
            ctx.intents = await self.intent_detector.detect(
                message=message,
                mercancia=mercancia_previa,
                contexto=" ".join(contexto_previo)
            )
            await self.log_event("INFO", f"Intenciones detectadas: {ctx.intents}", line_number=117)
            
            # 3. Generar prompts personalizados por intención
            ctx.prompts = await self.prompt_builder.build_prompts(
                user_id=user_id,
                message=message,
                intents=ctx.intents,
                contexto=contexto_previo
            )
            await self.log_event("INFO", f"Prompts generados: {len(ctx.prompts)}", line_number=125)
            
            # 4. Procesamiento especializado (fan-out paralelo)
            ctx.partial_responses = await self.dispatcher.dispatch(
                user_id=user_id,
                prompts_map=ctx.prompts,
                message=message,
                location=location
            )
            await self.log_event("INFO", f"Respuestas parciales recibidas: {len(ctx.partial_responses)}", line_number=133)
            print(f"Respuestas parciales recibidas: {len(ctx.partial_responses)}", flush=True)
            
            # 5. Unificar respuestas (mistral_service)
            if ctx.partial_responses:
                ctx.final_response = await self.response_unifier.unify(ctx.partial_responses)
                print(f"Respuestas final: {len(ctx.final_response)}", flush=True)
            else:
                ctx.final_response = "Lo siento, no pude procesar tu solicitud en este momento."
            
            await self.log_event("INFO", f"Respuesta unificada generada para {user_id}", line_number=141)
            
            # 6. Persistir contexto (asíncrono, no bloquea)
            if self.context_manager:
                asyncio.create_task(self._persist_context(ctx))
            
            ##################################################################################################
            # 7. ############# (AUN MODO REVISION-ITEGRACION) Pipeline n8n/Claude (modo desarrollo - asíncrono)
            # syncio.create_task(self._trigger_external_pipeline(ctx))
            
            # 8. Respuesta integrada del modelo
            return {"response": ctx.final_response}
            
        except Exception as e:
            await self.log_event("ERROR", f"Error en orquestación: {str(e)}", line_number=153)
            return {"response": "Lo siento, ocurrió un error interno. Por favor intenta de nuevo."}
    
    async def _persist_context(self, ctx: OrchestrationContext):
        """Persiste el contexto usando el esquema real activo del proyecto."""
        try:
            if self.context_manager:
                # Guardar historial del usuario en usuarios.contexto (esquema activo)
                # esta funcion trae incluida "_index_interaction_rag" la cual salva el contexto en
                # Chrome/Qdrant (revisar ContextManager.py Line 184)
                self.context_manager.save_context(
                    user_id=ctx.user_id,
                    user_msg=ctx.message,
                    ai_msg=ctx.final_response,
                    current_product_query=ctx.conversation_id,
                )

                # Guardar en ChromaDB/Qdrant (búsqueda semántica) si el backend está disponible
                if hasattr(self.context_manager, 'save_to_rag'):
                    await self.context_manager.save_to_rag(
                        user_id=ctx.user_id,
                        message=ctx.message,
                        response=ctx.final_response
                    )

            # Guardar en SQLite usando el modelo activo: conversaciones + mensajes
            if self.get_db:
                conn = self.get_db()
                cur = conn.cursor()

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS conversaciones (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        titulo TEXT,
                        es_flag INTEGER DEFAULT 0,
                        created_at TEXT,
                        updated_at TEXT
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS mensajes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id INTEGER NOT NULL,
                        user_id TEXT NOT NULL,
                        rol TEXT NOT NULL,
                        contenido TEXT NOT NULL,
                        created_at TEXT
                    )
                """)

                if ctx.conversation_id is None:
                    now = datetime.utcnow().isoformat()
                    cur.execute(
                        """
                        INSERT INTO conversaciones (user_id, titulo, es_flag, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (ctx.user_id, None, 0, now, now),
                    )
                    ctx.conversation_id = cur.lastrowid

                now = datetime.utcnow().isoformat()
                cur.execute(
                    """
                    INSERT INTO mensajes (conversation_id, user_id, rol, contenido, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (ctx.conversation_id, ctx.user_id, "user", ctx.message, now),
                )
                cur.execute(
                    """
                    INSERT INTO mensajes (conversation_id, user_id, rol, contenido, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (ctx.conversation_id, ctx.user_id, "assistant", ctx.final_response, now),
                )
                cur.execute(
                    "UPDATE conversaciones SET updated_at = ? WHERE id = ?",
                    (now, ctx.conversation_id),
                )

                conn.commit()
                conn.close()

            await self.log_event("INFO", f"Contexto persistido para {ctx.user_id}", line_number=196)
        except Exception as e:
            await self.log_event("ERROR", f"Error persistiendo contexto: {e}", line_number=198)
    
    async def _trigger_external_pipeline(self, ctx: OrchestrationContext):
        """
        Pipeline para integración futura con n8n y Claude.
        Modo desarrollo - completamente desacoplado del flujo principal.
        """
        try:
            # TODO: Implementar webhook hacia n8n/Claude
            # Esto permitirá automatizaciones externas y procesamiento adicional
            n8n_webhook_url = os.getenv("N8N_WEBHOOK_URL", "")
            if n8n_webhook_url:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(n8n_webhook_url, json={
                        "user_id": ctx.user_id,
                        "message": ctx.message,
                        "response": ctx.final_response,
                        "intents": ctx.intents,
                        "timestamp": datetime.utcnow().isoformat()
                    })
            claude_webhook_url = os.getenv("CLAUDE_WEBHOOK_URL", "")
            if claude_webhook_url:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(claude_webhook_url, json={
                        "user_id": ctx.user_id,
                        "conversation": {
                            "input": ctx.message,
                            "output": ctx.final_response,
                            "metadata": {
                                "intents": ctx.intents,
                                "duration_ms": (datetime.utcnow() - ctx.start_time).total_seconds() * 1000
                            }
                        }
                    })
        except Exception as e:
            # No loguear errores en pipeline externo para no saturar
            pass
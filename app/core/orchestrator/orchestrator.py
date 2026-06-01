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
6. Persiste contexto en SQLite/ChromaDB
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
        
        # URLs de microservicios (configurables vía environment)
        self.intent_service_url = os.getenv("INTENT_SERVICE_URL", "http://intent_service:9010")
        self.worker_service_url = os.getenv("WORKER_SERVICE_URL", "http://worker_service:9000")
        self.mistral_service_url = os.getenv("MISTRAL_SERVICE_URL", "http://mistral_service:9001")
        self.logging_ws_url = os.getenv("LOGGING_WS_URL", "ws://logging_service:8099/ws/logs")
        
        # URLs de servicios especializados (fan-out)
        self.specialized_services = {
            "REGISTRO": os.getenv("REGISTRO_SERVICE_URL", "http://registro_service:8010"),
            "CONTACTO": os.getenv("CONTACTO_SERVICE_URL", "http://contacto_service:8011"),
            "MENSAJERIA": os.getenv("MENSAJERIA_SERVICE_URL", "http://mensajeria_service:8012"),
            "VENTA": os.getenv("VENTA_SERVICE_URL", "http://venta_service:8013"),
            "COMPRA": os.getenv("COMPRA_SERVICE_URL", "http://compra_service:8014"),
            "INFORMATIVA": os.getenv("INFORMATIVA_SERVICE_URL", "http://informativa_service:8015"),
            "NOTIFICACION": os.getenv("NOTIFICACION_SERVICE_URL", "http://notificacion_service:8016"),
            "TRANSPORTE": os.getenv("TRANSPORTE_SERVICE_URL", "http://transporte_service:8017"),
            "SALUDO": os.getenv("SALUDO_SERVICE_URL", "http://saludo_service:8018"),
            "DESPEDIDA": os.getenv("DESPEDIDA_SERVICE_URL", "http://despedida_service:8019"),
            "RUTA": os.getenv("RUTA_SERVICE_URL", "http://ruta_service:8020"),
            "NEGOCIO": os.getenv("NEGOCIO_SERVICE_URL", "http://negocio_service:8021"),
            "SERVICIO": os.getenv("SERVICIO_SERVICE_URL", "http://servicio_service:8022"),
            "OTRA": os.getenv("OTRA_SERVICE_URL", "http://otra_service:8023")
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
            user_id: Identificador único del usuario
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
            
            # 1. Cargar contexto previo
            contexto_previo = []
            mercancia_previa = ""
            if self.context_manager:
                try:
                    contexto_previo, mercancia_previa = self.context_manager.load_context(user_id)
                    await self.log_event("INFO", f"Contexto cargado: {len(contexto_previo)} líneas, mercancía: {mercancia_previa}", line_number=107)
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
            
            # 5. Unificar respuestas (mistral_service)
            if ctx.partial_responses:
                ctx.final_response = await self.response_unifier.unify(ctx.partial_responses)
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
        """Persiste el contexto de la conversación en SQLite/ChromaDB."""
        try:
            if self.context_manager:
                # Guardar en contexto de memoria
                self.context_manager.save_context(
                    user_id=ctx.user_id,
                    message=ctx.message,
                    response=ctx.final_response,
                    conversation_id=ctx.conversation_id
                )
                
                # Guardar en ChromaDB (búsqueda semántica)
                if hasattr(self.context_manager, 'save_to_rag'):
                    await self.context_manager.save_to_rag(
                        user_id=ctx.user_id,
                        message=ctx.message,
                        response=ctx.final_response
                    )
                    
            # Guardar en SQLite
            if self.get_db:
                conn = self.get_db()
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO conversaciones (user_id, mensaje, respuesta, created_at) VALUES (?, ?, ?, ?)",
                    (ctx.user_id, ctx.message, ctx.final_response, datetime.utcnow().isoformat())
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
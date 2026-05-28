"""
HellenCommerce 2.0.1 - Orquestador Central (Librería Interna)

Este módulo actúa como el núcleo coordinador del sistema, NO como microservicio.
Es importado directamente por fastapi_service para orquestar todas las peticiones.

Arquitectura:
- FastAPI Ingress → Importa Orchestrator → Coordina microservicios especializados
- Comunicación asíncrona vía WebSocket con todos los servicios
- Fan-out/Fan-in paralelo para multi-intenciones
- Unificación de respuestas vía mistral_service
- Persistencia asíncrona en SQLite/ChromaDB
"""

from app.core.orchestrator.orchestrator import Orchestrator
from app.core.orchestrator.intent_detector import IntentDetector
from app.core.orchestrator.prompt_builder import PromptBuilderService
from app.core.orchestrator.specialized_dispatcher import SpecializedDispatcher
from app.core.orchestrator.response_unifier import ResponseUnifier
from app.core.orchestrator.logging_client import LoggingClient

__all__ = [
    "Orchestrator",
    "IntentDetector", 
    "PromptBuilderService",
    "SpecializedDispatcher",
    "ResponseUnifier",
    "LoggingClient"
]
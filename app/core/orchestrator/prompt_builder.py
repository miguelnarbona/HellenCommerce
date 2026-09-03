"""
HellenCommerce 2.0.1 - Prompt Builder Service

Componente del orquestador para construcción de prompts.
Se comunica con worker_service para generar prompts personalizados por intención.
"""

import httpx
import os
from typing import Dict, List


class PromptBuilderService:
    """Construye prompts personalizados para cada intención detectada."""
    
    def __init__(self, service_url: str = None, base_prompts_path: str = None):
        self.service_url = service_url or os.getenv("WORKER_SERVICE_URL", "http://worker_service:9000")
        from app.utils.paths import hc_path
        self.base_prompts_path = base_prompts_path or hc_path("app/prompts")
    
    async def build_prompts(
        self,
        user_id: str,
        message: str,
        intents: List[str],
        contexto: List[str] = None
    ) -> Dict[str, str]:
        """
        Genera un prompt personalizado para cada intención detectada.
        
        Args:
            user_id: Identificador del usuario
            message: Mensaje original del usuario
            intents: Lista de intenciones detectadas
            contexto: Contexto conversacional previo (opcional)
            
        Returns:
            Diccionario {intencion: prompt_construido}
        """
        try:
            payload = {
                "user_id": user_id,
                "message": message,
                "intents": intents,
                "contexto": contexto or []
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.service_url}/prompt",
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    prompts = data.get("prompts", {})
                    
                    # Si el worker no retornó prompts para todas las intenciones,
                    # generamos prompts por defecto
                    for intent in intents:
                        if intent not in prompts:
                            prompts[intent] = self._build_default_prompt(intent, message)
                    
                    return prompts
                else:
                    print(f"⚠️ Error en worker_service: {response.status_code}", flush=True)
                    return {intent: self._build_default_prompt(intent, message) for intent in intents}
                    
        except Exception as e:
            print(f"❌ Error construyendo prompts: {e}", flush=True)
            return {intent: self._build_default_prompt(intent, message) for intent in intents}
    
    def _build_default_prompt(self, intent: str, message: str) -> str:
        """
        Construye un prompt por defecto si el worker_service falla.
        """
        prompts_templates = {
            "REGISTRO": f"[REGISTRO] Usuario desea registrar información: {message}",
            "CONTACTO": f"[CONTACTO] Usuario solicita contacto: {message}",
            "MENSAJERIA": f"[MENSAJERIA] Usuario consulta sobre mensajería/envíos: {message}",
            "VENTA": f"[VENTA] Usuario quiere vender: {message}",
            "COMPRA": f"[COMPRA] Usuario quiere comprar: {message}",
            "INFORMATIVA": f"[INFORMATIVA] Usuario solicita información: {message}",
            "NOTIFICACION": f"[NOTIFICACION] Usuario desea notificaciones: {message}",
            "TRANSPORTE": f"[TRANSPORTE] Usuario consulta transporte: {message}",
            "SALUDO": f"[SALUDO] Usuario saluda: {message}",
            "DESPEDIDA": f"[DESPEDIDA] Usuario se despide: {message}",
            "RUTA": f"[RUTA] Usuario solicita ruta/indicaciones: {message}",
            "NEGOCIO": f"[NEGOCIO] Usuario consulta sobre negocios: {message}",
            "SERVICIO": f"[SERVICIO] Usuario consulta servicios: {message}",
            "OTRA": f"[OTRA] Consulta general: {message}"
        }
        return prompts_templates.get(intent, f"[OTRA] {message}")
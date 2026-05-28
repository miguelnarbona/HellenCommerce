"""
HellenCommerce 2.0.1 - Specialized Dispatcher

Componente del orquestador para despacho paralelo (fan-out) a microservicios especializados.
Ejecuta llamadas concurrentes a los servicios de categoría según las intenciones detectadas.
"""

import asyncio
import httpx
import os
from typing import Dict, List, Any


class SpecializedDispatcher:
    """Despacha prompts a microservicios especializados en paralelo (fan-out)."""
    
    def __init__(self, specialized_services: Dict[str, str] = None):
        self.specialized_services = specialized_services or {
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
    
    async def dispatch(
        self,
        user_id: str,
        prompts_map: Dict[str, str],
        message: str = "",
        location: str = None
    ) -> List[Dict[str, Any]]:
        """
        Despacha prompts a los microservicios especializados en paralelo.
        
        Args:
            user_id: Identificador del usuario
            prompts_map: Diccionario {intencion: prompt}
            message: Mensaje original (para fallback)
            location: Ubicación del usuario (para servicios de ruta/transporte)
            
        Returns:
            Lista de respuestas parciales de cada servicio
        """
        tasks = []
        
        for intent, prompt in prompts_map.items():
            service_url = self.specialized_services.get(intent)
            if not service_url:
                print(f"⚠️ Servicio no encontrado para intención: {intent}", flush=True)
                continue
            
            task = self._call_specialized_service(
                intent=intent,
                url=service_url,
                user_id=user_id,
                prompt=prompt,
                location=location
            )
            tasks.append(task)
        
        if not tasks:
            # Si no hay servicios especializados, retornar fallback
            return [{"intent": "FALLBACK", "partial": message, "error": "No services available"}]
        
        # Ejecutar todas las llamadas en paralelo (fan-out)
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filtrar respuestas válidas
        valid_responses = []
        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                intent = list(prompts_map.keys())[i] if i < len(prompts_map) else "UNKNOWN"
                print(f"❌ Error en {intent}: {response}", flush=True)
                valid_responses.append({
                    "intent": intent,
                    "partial": f"Error procesando {intent}",
                    "error": str(response)
                })
            elif isinstance(response, dict):
                valid_responses.append(response)
        
        return valid_responses
    
    async def _call_specialized_service(
        self,
        intent: str,
        url: str,
        user_id: str,
        prompt: str,
        location: str = None
    ) -> Dict[str, Any]:
        """
        Llama a un microservicio especializado específico.
        
        Args:
            intent: Tipo de intención
            url: URL base del servicio
            user_id: Identificador del usuario
            prompt: Prompt construido para esta intención
            location: Ubicación del usuario (opcional)
            
        Returns:
            Respuesta del servicio o error
        """
        try:
            payload = {
                "user_id": user_id,
                "prompt": prompt
            }
            if location:
                payload["location"] = location
            
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    f"{url}/process",
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "intent": data.get("intent", intent),
                        "partial": data.get("partial", ""),
                        "metadata": data.get("metadata", {})
                    }
                else:
                    return {
                        "intent": intent,
                        "partial": f"Error {response.status_code} en {intent}",
                        "error": f"HTTP {response.status_code}"
                    }
                    
        except asyncio.TimeoutError:
            return {
                "intent": intent,
                "partial": f"Timeout procesando {intent}",
                "error": "Timeout"
            }
        except Exception as e:
            return {
                "intent": intent,
                "partial": f"Error procesando {intent}",
                "error": str(e)
            }
"""
HellenCommerce 2.0.1 - Response Unifier

Componente del orquestador para unificación de respuestas.
Envía las respuestas parciales de los servicios especializados a mistral_service
para sintetizar una respuesta cohesiva, libre de errores y repeticiones.
"""

import httpx
import os
from typing import List, Dict, Any


class ResponseUnifier:
    """Unifica múltiples respuestas parciales en una sola respuesta cohesiva."""
    
    def __init__(self, mistral_service_url: str = None):
        # MISTRAL_SERVICE_URL=http://bunker_mistral_service:9001
        self.mistral_service_url = mistral_service_url or os.getenv("MISTRAL_SERVICE_URL", "http://bunker_mistral_service:9001")
    
    async def unify(self, partial_responses: List[Dict[str, Any]]) -> str:
        """
        Unifica las respuestas parciales de los servicios especializados.
        
        Args:
            partial_responses: Lista de respuestas parciales de cada servicio
            
        Returns:
            Respuesta unificada y cohesiva
        """
        try:
            # Si solo hay una respuesta y no tiene errores, retornarla directamente
            if len(partial_responses) == 1:
                response = partial_responses[0]
                if not response.get("error"):
                    return response.get("partial", "")
            
            # Filtrar respuestas con error
            valid_responses = [r for r in partial_responses if not r.get("error")]
            
            if not valid_responses:
                return "Lo siento, no pude procesar tu solicitud. Todos los servicios especializados reportaron errores."
            
            # Enviar a mistral_service para unificación
            payload = {
                "partials": valid_responses
            }
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.mistral_service_url}/synthesize",
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("response", "Error unificando la respuesta.")
                else:
                    # Fallback: concatenar respuestas si mistral falla
                    return self._fallback_unify(valid_responses)
                    
        except Exception as e:
            print(f"❌ Error unificando respuestas: {e}", flush=True)
            return self._fallback_unify(partial_responses)
    
    def _fallback_unify(self, responses: List[Dict[str, Any]]) -> str:
        """
        Unificación por fallback cuando mistral_service no está disponible.
        Concatena las respuestas de manera coherente.
        """
        if not responses:
            return "No hay información disponible."
        
        parts = []
        for response in responses:
            intent = response.get("intent", "OTRA")
            partial = response.get("partial", "")
            if partial:
                parts.append(f"[{intent}] {partial}")
        
        if len(parts) == 1:
            return parts[0]
        
        return "\n\n".join(parts)
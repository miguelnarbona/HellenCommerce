"""
HellenCommerce 2.0.1 - Intent Detector

Componente del orquestador para detección de intenciones.
Se comunica con intent_service vía HTTP para identificar una o múltiples intenciones.
"""

import httpx
import os
from typing import List


class IntentDetector:
    """Detecta intenciones del usuario consultando al intent_service."""
    
    def __init__(self, service_url: str = None):
        self.service_url = service_url or os.getenv("INTENT_SERVICE_URL", "http://intent_service:9010")
    
    async def detect(
        self,
        message: str,
        mercancia: str = "",
        contexto: str = ""
    ) -> List[str]:
        """
        Detecta una o múltiples intenciones para un mensaje dado.
        
        Args:
            message: Mensaje del usuario
            mercancia: Mercancía detectada en contexto previo (opcional)
            contexto: Contexto conversacional previo (opcional)
            
        Returns:
            Lista de intenciones detectadas (ej: ["COMPRA", "INFORMATIVA"])
        """
        try:
            payload = {
                "message": message,
                "mercancia": mercancia,
                "contexto": contexto
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.service_url}/intent",
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    intents = data.get("intents", [])
                    if not intents:
                        # Fallback a intención única si el servicio retorna formato antiguo
                        intent = data.get("intent", "OTRA")
                        intents = [intent] if intent else ["OTRA"]
                    return intents
                else:
                    print(f"⚠️ Error en intent_service: {response.status_code}", flush=True)
                    return ["OTRA"]
                    
        except Exception as e:
            print(f"❌ Error detectando intención: {e}", flush=True)
            return ["OTRA"]
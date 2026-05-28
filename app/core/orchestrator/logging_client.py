"""
HellenCommerce 2.0.1 - Logging Client

Componente del orquestador para envío de logs al subsistema de logging.
Se conecta vía WebSocket al logging_service para reportar eventos.
"""

import asyncio
import json
import os
import websockets
from datetime import datetime
from typing import Optional


class LoggingClient:
    """Cliente WebSocket para envío de logs al subsistema de logging."""
    
    def __init__(self, logging_ws_url: str = None):
        self.logging_ws_url = logging_ws_url or os.getenv("LOGGING_WS_URL", "ws://logging_service:8099/ws/logs")
        self._ws = None
        self._connected = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
    
    async def connect(self):
        """Establece conexión WebSocket con el logging_service."""
        if self._connected and self._ws:
            return
        
        try:
            self._ws = await websockets.connect(
                self.logging_ws_url,
                ping_interval=20,
                ping_timeout=10
            )
            self._connected = True
            self._reconnect_attempts = 0
        except Exception as e:
            print(f"⚠️ Error conectando a logging_service: {e}", flush=True)
            self._connected = False
    
    async def disconnect(self):
        """Cierra la conexión WebSocket."""
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._connected = False
    
    async def send_log(
        self,
        level: str,
        service_origin: str,
        source_file: str,
        line_number: int,
        message: str,
        error_description: str = "",
        proposed_solution: str = "",
        status_flag: str = "SOLUCIONADO"
    ):
        """
        Envía un log al subsistema de logging.
        
        Args:
            level: Nivel del log (ERROR, WARNING, INFO, DEBUG)
            service_origin: Nombre del servicio que origina el log
            source_file: Archivo fuente del evento
            line_number: Línea de código donde ocurrió
            message: Mensaje del log
            error_description: Descripción del error (si aplica)
            proposed_solution: Solución propuesta (si aplica)
            status_flag: Estado del log (PENDIENTE, SOLUCIONADO)
        """
        try:
            if not self._connected:
                await self.connect()
            
            if not self._connected or not self._ws:
                # Si no se puede conectar, imprimir en consola como fallback
                print(f"[{level}] {service_origin}/{source_file}:{line_number} - {message}", flush=True)
                return
            
            payload = {
                "timestamp": datetime.utcnow().isoformat(),
                "log_level": level,
                "service_origin": service_origin,
                "source_file": source_file,
                "line_number": line_number,
                "file_path": "",  # Se completa automáticamente en el servidor
                "code_snippet": message if level in ["ERROR", "WARNING"] else "",
                "error_description": error_description,
                "proposed_solution": proposed_solution,
                "status_flag": status_flag
            }
            
            await self._ws.send(json.dumps(payload))
            
        except Exception as e:
            print(f"⚠️ Error enviando log: {e}", flush=True)
            self._connected = False
            # Reintentar conexión en el próximo intento
            self._reconnect_attempts += 1
            if self._reconnect_attempts >= self._max_reconnect_attempts:
                print(f"❌ Máximo de reintentos alcanzado para logging", flush=True)
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
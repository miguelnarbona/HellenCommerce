import requests
from typing import Optional, Dict, Any


class MapLogic:
    """
    Módulo que conecta el worker_service con map_service.
    Se encarga de solicitar rutas y manejar errores de red o servicio.
    """

    def __init__(self, base_url: str = "http://map_service:5000"):
        # URL interna dentro de Docker (ambos servicios comparten hellen_net)
        self.base_url = base_url.rstrip("/")

    # ---------------------------------------------------------
    # RUTA ÓPTIMA ENTRE DOS PUNTOS
    # ---------------------------------------------------------
    def obtener_ruta(
        self,
        lat_origen: float,
        lon_origen: float,
        lat_destino: float,
        lon_destino: float,
        timeout: int = 5
    ) -> Optional[Dict[str, Any]]:
        """
        Solicita a map_service la ruta óptima entre dos puntos.
        Devuelve distancia, duración y polyline.
        Retorna None si hay error o no hay ruta.
        """

        url = f"{self.base_url}/ruta"
        params = {
            "lat_origen": lat_origen,
            "lon_origen": lon_origen,
            "lat_destino": lat_destino,
            "lon_destino": lon_destino,
        }

        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()

            if not data.get("success"):
                return None

            return {
                "country_code": data.get("country_code"),
                "osrm_base": data.get("osrm_base"),
                "distance_m": data["route"]["distance_m"],
                "duration_s": data["route"]["duration_s"],
                "polyline": data["route"]["polyline"],
            }

        except Exception:
            return None

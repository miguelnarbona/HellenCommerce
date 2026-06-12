import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

OSRM_SERVICES = {
    "cu": "http://osrm_cuba:5000",
    "mx": "http://osrm_mexico:5000",
    "us": "http://osrm_usa:5000",
}

DEFAULT_OSRM = "http://osrm_cuba:5000"


def detectar_pais(lat: float, lon: float) -> str:
    """
    Detecta el país usando reverse geocoding (Nominatim).
    Devuelve el código ISO del país en minúsculas (ej: 'cu', 'mx', 'us').
    """
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "zoom": 5,
        "addressdetails": 1,
    }
    headers = {
        "User-Agent": "hellencommerce-map-service/1.0"
    }

    try:
        r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        country_code = data.get("address", {}).get("country_code")
        return country_code.lower() if country_code else ""
    except Exception:
        return ""


def seleccionar_osrm(country_code: str) -> str:
    """
    Selecciona el OSRM adecuado según el país detectado.
    Si no existe o falla, usa el OSRM por defecto (Cuba).
    """
    if not country_code:
        return DEFAULT_OSRM
    return OSRM_SERVICES.get(country_code, DEFAULT_OSRM)


def llamar_osrm_route(osrm_base_url: str, lat1: float, lon1: float, lat2: float, lon2: float):
    """
    Llama al motor OSRM seleccionado para calcular la ruta óptima.
    Devuelve distancia, duración y polyline.
    """
    url = f"{osrm_base_url}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    params = {
        "overview": "full",
        "geometries": "polyline",
        "steps": "false",
    }

    try:
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()

        if not data.get("routes"):
            return None

        route = data["routes"][0]
        return {
            "distance_m": route["distance"],
            "duration_s": route["duration"],
            "polyline": route["geometry"],
        }
    except Exception:
        return None

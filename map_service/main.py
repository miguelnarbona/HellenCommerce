from fastapi import FastAPI, Query
import requests

from utils import detectar_pais, seleccionar_osrm, llamar_osrm_route


app = FastAPI(title="Map Service with OSRM routing")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

OSRM_SERVICES = {
    "cu": "http://osrm_cuba:5000",
    "ca": "http://osrm_canada:5000",
    "us": "http://osrm_usa:5000",
}

DEFAULT_OSRM = "http://osrm_cuba:5000"  # fallback inicial


def detectar_pais(lat: float, lon: float) -> str:
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "zoom": 5,
        "addressdetails": 1,
    }
    headers = {
        "User-Agent": "hellencommerce-map_services/1.0"
    }
    r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=5)
    r.raise_for_status()
    data = r.json()
    country_code = data.get("address", {}).get("country_code")
    return country_code.lower() if country_code else ""


def seleccionar_osrm(country_code: str) -> str:
    if not country_code:
        return DEFAULT_OSRM
    return OSRM_SERVICES.get(country_code, DEFAULT_OSRM)


def llamar_osrm_route(osrm_base_url: str, lat1: float, lon1: float, lat2: float, lon2: float):
    url = f"{osrm_base_url}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    params = {
        "overview": "full",
        "geometries": "polyline",
        "steps": "false",
    }
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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ruta")
def ruta(
    lat_origen: float = Query(...),
    lon_origen: float = Query(...),
    lat_destino: float = Query(...),
    lon_destino: float = Query(...),
):
    # 1) Detectar país según origen
    country_code = detectar_pais(lat_origen, lon_origen)

    # 2) Seleccionar OSRM adecuado
    osrm_base = seleccionar_osrm(country_code)

    # 3) Llamar a OSRM
    route = llamar_osrm_route(osrm_base, lat_origen, lon_origen, lat_destino, lon_destino)
    if route is None:
        return {
            "success": False,
            "message": "No se pudo calcular ruta",
            "country_code": country_code,
        }

    return {
        "success": True,
        "country_code": country_code,
        "osrm_base": osrm_base,
        "route": route,
    }

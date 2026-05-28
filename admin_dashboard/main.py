import asyncio
import os
import sys

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx

LOGGING_API_URL = os.getenv("LOGGING_API_URL", "http://logging_service:8099")

app = FastAPI(title="HellenCommerce Admin Dashboard")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/api/logs")
async def proxy_logs(service: str = None, level: str = None, limit: int = 100):
    params = {"limit": limit}
    if service: params["service"] = service
    if level:   params["level"]   = level
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{LOGGING_API_URL}/logs", params=params)
    return r.json()

@app.get("/api/hotfixes")
async def proxy_hotfixes(status: str = None):
    params = {}
    if status: params["status"] = status
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{LOGGING_API_URL}/hotfixes", params=params)
    return r.json()

@app.post("/api/hotfixes/{hotfix_id}/approve")
async def proxy_approve(hotfix_id: int, body: dict):
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{LOGGING_API_URL}/hotfixes/{hotfix_id}/approve", json=body)
    return r.json()

@app.post("/api/hotfixes/{hotfix_id}/reject")
async def proxy_reject(hotfix_id: int, body: dict):
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{LOGGING_API_URL}/hotfixes/{hotfix_id}/reject", json=body)
    return r.json()

@app.get("/api/stats")
async def proxy_stats():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{LOGGING_API_URL}/stats")
    return r.json()

@app.get("/health")
def health():
    return {"status": "ok"}

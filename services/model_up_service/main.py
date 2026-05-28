import asyncio
import os
import json
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

try:
    from llama_cpp import Llama
except Exception:
    Llama = None

# Simple model cache to avoid reloading models repeatedly
MODEL_CACHE: Dict[str, Any] = {}
MODEL_LOCK = asyncio.Lock()


class InferRequest(BaseModel):
    model: str
    prompt: str
    max_tokens: int = 256
    temperature: float = 0.2


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Model-up service ready
    yield


app = FastAPI(title="Model Up Service - Centralized Inference")


def _load_model(model_path: str):
    if Llama is None:
        raise RuntimeError("llama_cpp not available in model-up-service environment")
    # Create Llama instance with safe defaults
    return Llama(model_path=model_path, n_ctx=2048, n_threads=4, use_mmap=True, use_mlock=False)


async def get_model(model_path: str):
    async with MODEL_LOCK:
        if model_path in MODEL_CACHE:
            return MODEL_CACHE[model_path]
        # Load model in thread to avoid blocking event loop
        loop = asyncio.get_event_loop()
        model = await loop.run_in_executor(None, _load_model, model_path)
        MODEL_CACHE[model_path] = model
        return model


@app.post("/infer")
async def infer(req: InferRequest):
    model_path = req.model
    if not model_path:
        raise HTTPException(status_code=400, detail="Missing model path")

    try:
        model = await get_model(model_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading model: {e}")

    try:
        loop = asyncio.get_event_loop()
        # Run inference in executor to avoid blocking
        result = await loop.run_in_executor(
            None,
            lambda: model(prompt=req.prompt, max_tokens=req.max_tokens, temperature=req.temperature)
        )
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok", "models_loaded": list(MODEL_CACHE.keys())}

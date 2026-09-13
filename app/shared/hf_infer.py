"""
HellenCommerce - HuggingFace Inference Client compartido
========================================================
Módulo ligero y sin dependencias pesadas para realizar inferencia
remota con Mistral-7B-Instruct-v0.2 via HuggingFace Serverless API.

Reemplaza todas las llamadas HTTP locales a model_up_service:8040/infer.

Uso en cualquier servicio especializado:
    from app.shared.hf_infer import call_mistral

    partial = await call_mistral(prompt_mistral, fallback="Respuesta por defecto.")

Variables de entorno:
    HF_TOKEN — Token de HuggingFace (requerido para inferencia serverless).
               Obtener en: https://huggingface.co/settings/tokens
"""

import asyncio
import os
from huggingface_hub import InferenceClient
import requests
from typing import Mapping

# ---------------------------------------------------------------------------
# Configuración centralizada
# ---------------------------------------------------------------------------
HF_MODEL_CANDIDATES = [
    os.getenv("HF_MODEL"),
    "Qwen/Qwen3-14B",
    "Qwen/Qwen3-32B",
    "deepseek-ai/DeepSeek-V3.1",
    "deepseek-ai/DeepSeek-V4-Flash",
]
HF_MODEL_CANDIDATES = [m for m in HF_MODEL_CANDIDATES if m]
_HF_MODEL = HF_MODEL_CANDIDATES[0] if HF_MODEL_CANDIDATES else "Qwen/Qwen3-14B"
_MAX_TOKENS = 300
_TEMPERATURE = 0.4

# Cliente singleton — se inicializa una sola vez por proceso.
# InferenceClient es thread-safe y reutilizable.
_hf_client: InferenceClient | None = None


def _get_client() -> InferenceClient:
    """Retorna el cliente HF singleton, inicializándolo si es necesario."""
    global _hf_client
    if _hf_client is None:
        token = os.getenv("HF_TOKEN", "").strip()
        if not token:
            print("⚠️  HF_TOKEN no configurado. Las llamadas a HF API pueden fallar.", flush=True)
        _hf_client = InferenceClient(token=token or None)
        print(f"✅ HF InferenceClient inicializado → modelo: {_HF_MODEL}", flush=True)
    return _hf_client


def _extract_hf_text(response) -> str:
    """Extrae texto limpio de una respuesta de HuggingFace o devuelve cadena vacía."""
    if response is None:
        return ""
    try:
        # Soporta objetos con atributos (InferenceClient) y dicts (HTTP router)
        # 1) Si es un mapping (dict-like), navegar claves esperadas
        if isinstance(response, dict):
            choices = response.get("choices") or []
            if not choices:
                return ""
            first_choice = choices[0]
            message = first_choice.get("message") if isinstance(first_choice, dict) else None
            if message:
                for field_name in ("content", "reasoning_content", "reasoning"):
                    value = message.get(field_name) if isinstance(message, dict) else None
                    if value:
                        return str(value).strip()
            for field_name in ("text", "content"):
                value = first_choice.get(field_name) if isinstance(first_choice, dict) else None
                if value:
                    return str(value).strip()

        # 2) Si es un objeto con atributos (InferenceClient response)
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""

        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        if message is not None:
            for field_name in ("content", "reasoning_content", "reasoning"):
                value = getattr(message, field_name, None)
                if value is not None:
                    if isinstance(value, str):
                        return value.strip()
                    return str(value).strip()

        for field_name in ("text", "content"):
            value = getattr(first_choice, field_name, None)
            if value is not None:
                if isinstance(value, str):
                    return value.strip()
                return str(value).strip()
    except Exception:
        return ""
    return ""


# ---------------------------------------------------------------------------
# Función principal de inferencia (síncrona — para usar con asyncio.to_thread)
# ---------------------------------------------------------------------------
def _infer_sync(prompt: str) -> str:
    """
    Llama al modelo Mistral-7B vía HuggingFace Serverless Inference API.
    Retorna el string de respuesta generado.

    Usa chat_completion con el formato [INST]...[/INST] nativo de Mistral.
    Si el prompt ya tiene ese formato, se envía tal cual como contenido del
    mensaje 'user'; el modelo lo interpreta correctamente.
    """
    client = _get_client()

    # Probar el modelo configurado y, si falla por proveedor no habilitado,
    # reintentar con candidatos compatibles hasta encontrar uno que responda.
    for model_name in HF_MODEL_CANDIDATES:
        try:
            response = client.chat_completion(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=_MAX_TOKENS,
                temperature=_TEMPERATURE,
            )
            text = _extract_hf_text(response)
            if text:
                return text
        except Exception:
            # intentar el router HTTP si el cliente falla (DNS o shape distinto)
            try:
                text = _infer_via_router(model_name, prompt)
                if text:
                    return text
            except Exception:
                continue

    raise RuntimeError("Ningún modelo HF compatible respondió en este proveedor.")


def _infer_via_router(model_name: str, prompt: str) -> str:
    """
    Fallback que llama al endpoint `router.huggingface.co/v1/chat/completions`.
    Usa formato JSON del nuevo endpoint: {"model":..., "messages": [...]}
    Retorna string con la primera salida o cadena vacía.
    """
    token = (os.getenv("HF_TOKEN", "") or "").strip()
    if not token:
        raise RuntimeError("HF_TOKEN ausente para llamada al router HF")

    url = "https://router.huggingface.co/v1/chat/completions"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": _MAX_TOKENS,
        "temperature": _TEMPERATURE,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # data is a dict-like response; extract text
    return _extract_hf_text(data)


def call_chat_model(model_name: str, messages: list, max_tokens: int = None, temperature: float = None) -> str:
    """
    Llamada unificada para chat completions.
    Intenta usar el `InferenceClient` localmente; si falla, hace POST al `router.huggingface.co`.
    `messages` debe ser una lista de dicts con `role`/`content`.
    """
    client = _get_client()
    mt = max_tokens or _MAX_TOKENS
    temp = temperature if temperature is not None else _TEMPERATURE

    # Intentar vía InferenceClient primero
    try:
        response = client.chat_completion(model=model_name, messages=messages, max_tokens=mt, temperature=temp)
        text = _extract_hf_text(response)
        if text:
            return text
    except Exception:
        pass

    # Fallback al router HTTP
    token = (os.getenv("HF_TOKEN", "") or "").strip()
    if not token:
        raise RuntimeError("HF_TOKEN ausente para llamada al router HF")

    url = "https://router.huggingface.co/v1/chat/completions"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"model": model_name, "messages": messages, "max_tokens": mt, "temperature": temp}
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return _extract_hf_text(data)


# ---------------------------------------------------------------------------
# Wrapper asíncrono — compatible con el event loop de FastAPI
# ---------------------------------------------------------------------------
async def call_mistral(prompt: str, fallback: str = "") -> str:
    """
    Realiza inferencia remota con Mistral-7B-Instruct-v0.2 vía HuggingFace.

    Ejecuta la llamada en un thread separado para no bloquear el event loop
    asíncrono de FastAPI (InferenceClient es síncrono internamente).

    Args:
        prompt:   El prompt completo en formato [INST]...[/INST] o texto libre.
        fallback: String a retornar si la API falla (error de red, timeout, etc.)

    Returns:
        String con la respuesta generada por el modelo, o el fallback si hay error.

    Ejemplo:
        prompt = '''[INST] Eres un asistente de COMPRA.
        El usuario preguntó: Busco arroz en Bogotá.
        Responde conciso. [/INST]'''
        
        respuesta = await call_mistral(prompt, fallback="No pude generar respuesta.")
    """
    try:
        result = await asyncio.to_thread(_infer_sync, prompt)
        return result
    except Exception as e:
        # Log mínimo a stdout para que cada servicio deje evidencia real del problema
        print(f"⚠️  HF inference error: {type(e).__name__}: {e}", flush=True)
        print(f"⚠️  HF candidates probados: {HF_MODEL_CANDIDATES}", flush=True)
        print(f"⚠️  HF_TOKEN configurado: {bool((os.getenv('HF_TOKEN', '') or '').strip())}", flush=True)
        return fallback

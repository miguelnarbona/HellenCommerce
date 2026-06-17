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

# ---------------------------------------------------------------------------
# Configuración centralizada
# ---------------------------------------------------------------------------
_HF_MODEL   = "mistralai/Mistral-7B-Instruct-v0.2"
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

    # HF chat_completion con messages API (compatible con Mistral instruct)
    response = client.chat_completion(
        model=_HF_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=_MAX_TOKENS,
        temperature=_TEMPERATURE,
    )
    # Extraer el string de la respuesta
    return response.choices[0].message.content.strip()


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
        # Log mínimo a stdout (cada servicio ya tiene su propio logger)
        print(f"⚠️  HF inference error: {type(e).__name__}: {e}", flush=True)
        return fallback

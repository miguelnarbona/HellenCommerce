# app/adapters/models/MistralModel.py

from app.adapters.models.IModelExecutor import IModelExecutor
import asyncio
import subprocess
import json
import httpx
import os

class MistralModel(IModelExecutor):

    def __init__(self, model_path: str, n_ctx: int = 1024, n_threads: int = 6):
        self.TIMEOUT = 3
        self.HF_API_KEY = os.getenv("HF_API_KEY")
        # self.HF_API_KEY = "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"
        # self.HF_MODEL = "mistralai/phi-2-instruct.Q4_K_S"
        self.HF_MODEL = "mistral/Mistral-7B-Instruct-v0.2"

    # ==========================================================
    #   LOCAL (proceso separado con timeout real)
    # ==========================================================
    async def _infer_local(self, prompt: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "python3", "/local_worker_service/local_worker.py",
            # "python3", "/worker_service/main.py",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        proc.stdin.write(json.dumps({"prompt": prompt}).encode() + b"\n")
        await proc.stdin.drain()

        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=self.TIMEOUT)
            data = json.loads(line.decode())
            return data["response"]

        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError("Modelo local tardó demasiado")

    # ==========================================================
    #   REMOTO (HuggingFace)
    # ==========================================================
    async def _infer_remote(self, prompt: str) -> str:
        headers = {"Authorization": f"Bearer {self.HF_API_KEY}"}
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 80,
                "temperature": 0.7,
                "top_p": 0.9
            }
        }

        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(
                f"https://api-inference.huggingface.co/models/{self.HF_MODEL}",
                headers=headers,
                json=payload
            )
            data = r.json()
            return data[0]["generated_text"]

    # ==========================================================
    #   API ASYNC HÍBRIDA
    # ==========================================================
    async def generate_async(self, prompt: str) -> str:
        try:
            return await self._infer_local(prompt)
        except Exception:
            return await self._infer_remote(prompt)

    # ==========================================================
    #   API SYNC (usada por pipeline)
    # ==========================================================
    def generate(self, prompt: str) -> str:
        return asyncio.run(self.generate_async(prompt))

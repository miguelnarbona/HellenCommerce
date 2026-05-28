# adapters/models/MistralModel.py

from llama_cpp import Llama
from app.adapters.models.IModelExecutor import IModelExecutor
import asyncio
import httpx
import os


class MistralModel(IModelExecutor):

    def __init__(self, model_path: str, n_ctx: int = 2048, n_threads: int = 2):
        # Modelo local (CPU)
        self.llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_batch=128,
            use_mmap=True,
            use_mlock=False,
            verbose=False,
        )

        # Configuración del fallback remoto
        # self.HF_API_KEY = os.getenv("HF_API_KEY")
        self.HF_API_KEY = "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"
        self.HF_MODEL = "mistralai/Mistral-7B-Instruct-v0.2"
        self.TIMEOUT = 3  # segundos

    # ==========================================================
    #   INFERENCIA REMOTA (HuggingFace) — respeta el prompt completo
    # ==========================================================
    async def _infer_remote(self, prompt: str) -> str:
        headers = {"Authorization": f"Bearer {self.HF_API_KEY}"}
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 200,
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
    #   INFERENCIA LOCAL (streaming)
    # ==========================================================
    def _infer_local(self, prompt: str) -> str:
        chunks = []
        for chunk in self.llm(
            prompt=prompt,
            max_tokens=160,
            temperature=0.65,
            top_p=0.85,
            top_k=40,
            stop=["</s>"],
            echo=False,
            stream=True
        ):
            token = chunk["choices"][0]["text"]
            chunks.append(token)

        return "".join(chunks).strip()

    # ==========================================================
    #   LÓGICA HÍBRIDA: local con timeout + fallback remoto
    # ==========================================================
    async def generate_async(self, prompt: str) -> str:
        loop = asyncio.get_event_loop()

        try:
            # Intentar local con timeout
            local_task = loop.run_in_executor(None, self._infer_local, prompt)
            return await asyncio.wait_for(local_task, timeout=self.TIMEOUT)

        except asyncio.TimeoutError:
            print(">>> TIMEOUT LOCAL: usando Mistral 7B Instruct remoto", flush=True)
            return await self._infer_remote(prompt)

        except Exception as e:
            print(">>> ERROR LOCAL:", e, flush=True)
            return await self._infer_remote(prompt)

    # ==========================================================
    #   API SÍNCRONA — usada por director y todo tu pipeline
    # ==========================================================
    def generate(self, prompt: str) -> str:
        return asyncio.run(self.generate_async(prompt))

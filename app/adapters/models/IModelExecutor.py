# adapters/models/IModelExecutor.py
from abc import ABC, abstractmethod

class IModelExecutor(ABC):

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Genera una respuesta a partir de un prompt."""
        pass
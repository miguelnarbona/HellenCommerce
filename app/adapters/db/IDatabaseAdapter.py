# adapters/db/IDatabaseAdapter.py
from abc import ABC, abstractmethod

class IDatabaseAdapter(ABC):

    @abstractmethod
    def insert_user(self, data: dict):
        pass

    @abstractmethod
    def search_matches(self, role: str, item: str):
        pass

    @abstractmethod
    def process_prompt(self, message: str, role: str, user_id: str) -> dict:
        pass
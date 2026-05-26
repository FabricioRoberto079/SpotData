from abc import ABC, abstractmethod
from typing import AsyncIterator


class IChatService(ABC):
    @abstractmethod
    def list(
        self, folder_id: str | None = None, user_id: str | None = None
    ) -> list[dict]: ...

    @abstractmethod
    def get(self, chat_id: str, user_id: str | None = None) -> dict: ...

    @abstractmethod
    def update(
        self, chat_id: str, fields: dict, user_id: str | None = None
    ) -> dict: ...

    @abstractmethod
    def delete(self, chat_id: str, user_id: str | None = None) -> None: ...

    @abstractmethod
    async def ask_stream(
        self,
        question: str,
        chat_id: str | None = None,
        user_id: str | None = None,
    ) -> AsyncIterator[dict]: ...

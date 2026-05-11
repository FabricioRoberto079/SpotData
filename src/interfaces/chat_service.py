from abc import ABC, abstractmethod


class IChatService(ABC):
    @abstractmethod
    def list(self, folder_id: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get(self, chat_id: str) -> dict: ...

    @abstractmethod
    def update(self, chat_id: str, fields: dict) -> dict: ...

    @abstractmethod
    def delete(self, chat_id: str) -> None: ...

    @abstractmethod
    def ask(
        self,
        question: str,
        chat_id: str | None = None,
        user_id: str | None = None,
        n_results: int = 5,
    ) -> dict: ...

    @abstractmethod
    def get_message(self, message_id: str) -> dict: ...

    @abstractmethod
    def delete_message(self, message_id: str) -> None: ...

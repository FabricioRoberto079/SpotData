from abc import ABC, abstractmethod


class IUploadSessionService(ABC):
    @abstractmethod
    def create_session(
        self,
        file_name: str,
        total_size: int,
        user_id: str,
        category_id: str | None = None,
    ) -> dict: ...

    @abstractmethod
    def get_status(self, session_id: str, user_id: str) -> dict: ...

    @abstractmethod
    def append_chunk(
        self,
        session_id: str,
        user_id: str,
        offset: int,
        chunk: bytes,
    ) -> dict: ...

    @abstractmethod
    def pause(self, session_id: str, user_id: str) -> dict: ...

    @abstractmethod
    def complete(self, session_id: str, user_id: str) -> dict: ...

    @abstractmethod
    def abort(self, session_id: str, user_id: str) -> None: ...

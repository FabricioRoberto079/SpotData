from abc import ABC, abstractmethod

from src.enums.content_type import ContentType


class IDocumentService(ABC):
    @abstractmethod
    def create_document(
        self,
        file_name: str,
        folder_id: str | None = None,
        uploaded_by: str | None = None,
    ) -> str: ...

    @abstractmethod
    def add_version(
        self,
        document_id: str,
        file_data: bytes,
        content_type: ContentType,
    ) -> dict: ...

    @abstractmethod
    def upload_new_document(
        self,
        file_data: bytes,
        content_type: ContentType,
        file_name: str,
        folder_id: str | None = None,
        uploaded_by: str | None = None,
    ) -> dict: ...

    @abstractmethod
    def get_version_file(
        self, document_id: str, version_number: int | None = None
    ) -> tuple[bytes, str, str, int]: ...

    @abstractmethod
    def list_documents(
        self,
        folder_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict: ...

    @abstractmethod
    def get_document(self, document_id: str) -> dict: ...

    @abstractmethod
    def update_document(
        self,
        document_id: str,
        file_name: str | None = None,
        folder_id: str | None = None,
        clear_folder: bool = False,
    ) -> dict: ...

    @abstractmethod
    def delete_document(self, document_id: str) -> None: ...

    @abstractmethod
    def retry_vectorization(self, document_id: str, version_number: int) -> dict: ...

    @abstractmethod
    def list_versions(self, document_id: str) -> list[dict]: ...

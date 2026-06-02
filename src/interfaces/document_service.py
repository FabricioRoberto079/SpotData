from abc import ABC, abstractmethod

from src.enums.content_type import ContentType
from src.enums.document_category import DocumentCategory


class IDocumentService(ABC):
    @abstractmethod
    def create_document(
        self,
        file_name: str,
        category: DocumentCategory,
        uploaded_by: str | None = None,
        category_id: str | None = None,
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
        category: DocumentCategory,
        uploaded_by: str | None = None,
        category_id: str | None = None,
        allowed_category_ids: list[str] | None = None,
    ) -> dict: ...

    @abstractmethod
    def get_version_file(
        self,
        document_id: str,
        version_number: int | None = None,
        allowed_category_ids: list[str] | None = None,
    ) -> tuple[bytes, str, str, int]: ...

    @abstractmethod
    def list_documents(
        self,
        category_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        allowed_category_ids: list[str] | None = None,
    ) -> dict: ...

    @abstractmethod
    def get_document(
        self, document_id: str, allowed_category_ids: list[str] | None = None
    ) -> dict: ...

    @abstractmethod
    def delete_document(
        self, document_id: str, allowed_category_ids: list[str] | None = None
    ) -> None: ...

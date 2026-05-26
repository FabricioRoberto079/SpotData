from abc import ABC, abstractmethod
from dataclasses import dataclass

from fastapi import UploadFile

from src.enums.content_type import ContentType
from src.enums.document_category import DocumentCategory


@dataclass(frozen=True, slots=True)
class UploadPayload:
    file_data: bytes
    content_type: ContentType
    file_name: str
    category: DocumentCategory


class IUploadStrategy(ABC):
    @abstractmethod
    async def build_payload(
        self,
        *,
        file: UploadFile | None,
        text: str | None,
        file_name: str | None,
    ) -> UploadPayload: ...

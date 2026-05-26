from abc import ABC, abstractmethod

from src.enums.content_type import ContentType


class ITextExtractor(ABC):
    @abstractmethod
    def extract_from_bytes(self, data: bytes, content_type: ContentType) -> str: ...

    @abstractmethod
    def extract_pages_from_bytes(
        self, data: bytes, content_type: ContentType
    ) -> list[str] | None: ...

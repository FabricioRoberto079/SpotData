from abc import ABC, abstractmethod


class IContentExtractor(ABC):
    @abstractmethod
    def from_bytes(self, data: bytes) -> str: ...

    def pages_from_bytes(self, data: bytes) -> list[str] | None:
        return None

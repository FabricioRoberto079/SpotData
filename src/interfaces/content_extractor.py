from abc import ABC, abstractmethod


class IContentExtractor(ABC):
    @abstractmethod
    def from_path(self, file_path: str) -> str: ...

    @abstractmethod
    def from_bytes(self, data: bytes) -> str: ...

from abc import ABC, abstractmethod


class ITextChunker(ABC):
    @abstractmethod
    def chunk(
        self,
        text: str,
        max_chars: int | None = None,
        overlap: int | None = None,
    ) -> list[str]: ...

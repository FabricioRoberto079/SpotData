from typing import Protocol


class ContentExtractorProtocol(Protocol):
    def from_bytes(self, data: bytes) -> str: ...

    def pages_from_bytes(self, data: bytes) -> list[str] | None: ...

from src.interfaces.content_extractor import IContentExtractor


def _decode(data: bytes) -> str:
    """Best-effort text decode: try utf-8 first, fall back to latin-1 with replacement.
    Avoids raising 500s for upload data that's mostly text but has stray non-utf8 bytes."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


class PlainTextExtractor(IContentExtractor):
    def from_bytes(self, data: bytes) -> str:
        return _decode(data).strip()

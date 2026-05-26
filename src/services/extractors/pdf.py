import io

from pypdf import PdfReader

from src.interfaces.content_extractor import IContentExtractor


class PdfExtractor(IContentExtractor):
    @staticmethod
    def _pages(reader: PdfReader) -> list[str]:
        return [(p.extract_text() or "").strip() for p in reader.pages]

    @classmethod
    def _read(cls, reader: PdfReader) -> str:
        return "\n".join(page for page in cls._pages(reader) if page).strip()

    def from_bytes(self, data: bytes) -> str:
        return self._read(PdfReader(io.BytesIO(data)))

    def pages_from_bytes(self, data: bytes) -> list[str]:
        return self._pages(PdfReader(io.BytesIO(data)))

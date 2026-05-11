import io

from pypdf import PdfReader

from src.interfaces.content_extractor import IContentExtractor


class PdfExtractor(IContentExtractor):
    @staticmethod
    def _read(reader: PdfReader) -> str:
        pages = [p.extract_text() for p in reader.pages if p.extract_text()]
        return "\n".join(pages).strip()

    def from_path(self, file_path: str) -> str:
        return self._read(PdfReader(file_path))

    def from_bytes(self, data: bytes) -> str:
        return self._read(PdfReader(io.BytesIO(data)))

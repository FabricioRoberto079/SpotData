from src.enums.content_type import ContentType
from src.exceptions import ValidationError
from src.protocols.content_extractor import ContentExtractorProtocol
from src.services.extractors.image import ImageExtractor
from src.services.extractors.pdf import PdfExtractor
from src.services.extractors.plain_text import PlainTextExtractor
from src.services.extractors.word import WordExtractor


class TextExtractor:
    def __init__(self, registry: dict[ContentType, ContentExtractorProtocol] | None = None) -> None:
        self._registry = registry or {
            ContentType.TEXT: PlainTextExtractor(),
            ContentType.PDF: PdfExtractor(),
            ContentType.IMAGE: ImageExtractor(),
            ContentType.DOC: WordExtractor(),
        }

    def _resolve(self, content_type: ContentType) -> ContentExtractorProtocol:
        extractor = self._registry.get(content_type)
        if extractor is None:
            raise ValidationError(f"Unsupported type: {content_type}")
        return extractor

    def extract_from_bytes(self, data: bytes, content_type: ContentType) -> str:
        return self._resolve(content_type).from_bytes(data)

    def extract_pages_from_bytes(self, data: bytes, content_type: ContentType) -> list[str] | None:
        return self._resolve(content_type).pages_from_bytes(data)


def get_text_extractor() -> TextExtractor:
    return TextExtractor()

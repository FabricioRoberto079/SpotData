from src.enums.content_type import ContentType
from src.exceptions import ValidationError
from src.interfaces.content_extractor import IContentExtractor
from src.interfaces.text_extractor import ITextExtractor
from src.services.extractors.image import ImageExtractor
from src.services.extractors.pdf import PdfExtractor
from src.services.extractors.plain_text import PlainTextExtractor
from src.services.extractors.word import WordExtractor


class TextExtractor(ITextExtractor):
    def __init__(
        self, registry: dict[ContentType, IContentExtractor] | None = None
    ) -> None:
        self._registry = registry or {
            ContentType.TEXTO: PlainTextExtractor(),
            ContentType.PDF: PdfExtractor(),
            ContentType.FOTO: ImageExtractor(),
            ContentType.DOC: WordExtractor(),
        }

    def _resolve(self, content_type: ContentType) -> IContentExtractor:
        extractor = self._registry.get(content_type)
        if extractor is None:
            raise ValidationError(f"Unsupported type: {content_type}")
        return extractor

    def extract_from_bytes(self, data: bytes, content_type: ContentType) -> str:
        return self._resolve(content_type).from_bytes(data)

    def extract_pages_from_bytes(
        self, data: bytes, content_type: ContentType
    ) -> list[str] | None:
        return self._resolve(content_type).pages_from_bytes(data)


def get_text_extractor() -> ITextExtractor:
    return TextExtractor()

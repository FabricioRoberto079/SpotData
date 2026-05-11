import pytest

from src.enums.content_type import ContentType
from src.exceptions import ValidationError
from src.interfaces.content_extractor import IContentExtractor
from src.services.text_extractor import TextExtractor


class _Stub(IContentExtractor):
    def __init__(self, value: str):
        self.value = value
        self.from_bytes_calls: list[bytes] = []

    def from_path(self, file_path):
        return self.value

    def from_bytes(self, data):
        self.from_bytes_calls.append(data)
        return self.value


def test_dispatches_per_content_type():
    pdf = _Stub("PDF")
    txt = _Stub("TXT")
    extractor = TextExtractor({ContentType.PDF: pdf, ContentType.TEXTO: txt})
    assert extractor.extract_from_bytes(b"x", ContentType.PDF) == "PDF"
    assert extractor.extract_from_bytes(b"x", ContentType.TEXTO) == "TXT"
    assert pdf.from_bytes_calls == [b"x"]


def test_unsupported_type_raises_validation_error():
    extractor = TextExtractor({ContentType.PDF: _Stub("x")})
    with pytest.raises(ValidationError):
        extractor.extract_from_bytes(b"x", ContentType.FOTO)


def test_plain_text_extractor_decodes_utf8():
    from src.services.extractors.plain_text import PlainTextExtractor

    assert PlainTextExtractor().from_bytes("olá".encode("utf-8")) == "olá"

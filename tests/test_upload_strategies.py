import asyncio
import io

import pytest
from fastapi import UploadFile

from src.exceptions import ValidationError

from src.enums.content_type import ContentType
from src.enums.document_category import DocumentCategory
from src.enums.upload_kind import UploadKind
from src.services.upload_strategies import (
    FileUploadStrategy,
    ImageUploadStrategy,
    TextUploadStrategy,
    get_upload_strategy,
)
from src.services.upload_strategies._shared import MAX_UPLOAD_SIZE


def _run(coro):
    return asyncio.run(coro)


def _upload(filename: str, data: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data))


def test_file_strategy_pdf_maps_to_document_category():
    payload = _run(
        FileUploadStrategy().build_payload(
            file=_upload("report.pdf", b"%PDF-..."), text=None, file_name=None
        )
    )
    assert payload.content_type == ContentType.PDF
    assert payload.category == DocumentCategory.DOCUMENTS
    assert payload.file_name == "report.pdf"
    assert payload.file_data == b"%PDF-..."


def test_file_strategy_txt_maps_to_text_category():
    payload = _run(
        FileUploadStrategy().build_payload(
            file=_upload("notes.txt", b"hello"), text=None, file_name="override.txt"
        )
    )
    assert payload.content_type == ContentType.TEXTO
    assert payload.category == DocumentCategory.TEXT
    assert payload.file_name == "override.txt"


def test_file_strategy_rejects_unknown_extension():
    with pytest.raises(ValidationError):
        _run(
            FileUploadStrategy().build_payload(
                file=_upload("data.csv", b"a,b"), text=None, file_name=None
            )
        )


def test_file_strategy_requires_file():
    with pytest.raises(ValidationError):
        _run(FileUploadStrategy().build_payload(file=None, text=None, file_name=None))


_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_image_strategy_accepts_png():
    payload = _run(
        ImageUploadStrategy().build_payload(
            file=_upload("pic.PNG", _PNG_BYTES), text=None, file_name=None
        )
    )
    assert payload.content_type == ContentType.FOTO
    assert payload.category == DocumentCategory.IMAGES
    assert payload.file_name == "pic.PNG"


def test_image_strategy_rejects_pdf():
    with pytest.raises(ValidationError):
        _run(
            ImageUploadStrategy().build_payload(
                file=_upload("x.pdf", b"%PDF"), text=None, file_name=None
            )
        )


def test_text_strategy_encodes_and_defaults_name():
    payload = _run(
        TextUploadStrategy().build_payload(
            file=None, text="  some content  ", file_name=None
        )
    )
    assert payload.file_data == "some content".encode("utf-8")
    assert payload.content_type == ContentType.TEXTO
    assert payload.category == DocumentCategory.TEXT
    assert payload.file_name == "plain-text"


def test_text_strategy_uses_provided_name():
    payload = _run(
        TextUploadStrategy().build_payload(file=None, text="x", file_name="memo")
    )
    assert payload.file_name == "memo"


def test_text_strategy_rejects_empty():
    with pytest.raises(ValidationError):
        _run(TextUploadStrategy().build_payload(file=None, text="   ", file_name=None))


def test_text_strategy_rejects_oversized():
    with pytest.raises(ValidationError):
        _run(
            TextUploadStrategy().build_payload(
                file=None, text="x" * (MAX_UPLOAD_SIZE + 1), file_name=None
            )
        )


def test_registry_resolves_all_kinds():
    assert isinstance(get_upload_strategy(UploadKind.FILE), FileUploadStrategy)
    assert isinstance(get_upload_strategy(UploadKind.IMAGE), ImageUploadStrategy)
    assert isinstance(get_upload_strategy(UploadKind.TEXT), TextUploadStrategy)

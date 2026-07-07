"""Batch upload endpoint: kind inference per extension and per-file isolation
(one bad file reports an error in its item instead of failing the batch).

The endpoint coroutine is called directly with a stub IDocumentService, the
same style test_upload_strategies uses — no HTTP/auth layer involved.
"""
import asyncio
import io

import pytest
from fastapi import UploadFile

from src.controllers.document_controller import upload_documents_batch
from src.enums.content_type import ContentType
from src.exceptions import ValidationError
from src.interfaces.document_service import IDocumentService
from src.models.user import User

_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _upload(filename: str, data: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data))


def _user() -> User:
    return User(id="u1", name="u1", email="u1@x.com", password_hash="!disabled!")


class _StubDocumentService(IDocumentService):
    def __init__(self, fail_names: set[str] | None = None):
        self.uploads: list[dict] = []
        self._fail_names = fail_names or set()

    def upload_new_document(
        self,
        file_data,
        content_type,
        file_name,
        category,
        uploaded_by=None,
        category_id=None,
    ):
        if file_name in self._fail_names:
            raise ValidationError("No text extracted from uploaded content.")
        self.uploads.append(
            {
                "file_name": file_name,
                "content_type": content_type,
                "uploaded_by": uploaded_by,
                "category_id": category_id,
            }
        )
        return {
            "document_id": f"doc-{len(self.uploads)}",
            "file_name": file_name,
            "category": category.value,
            "created": True,
            "version": {"version_number": 1},
        }

    def create_document(self, file_name, category, uploaded_by=None, category_id=None):
        raise NotImplementedError

    def add_version(self, document_id, file_data, content_type):
        raise NotImplementedError

    def get_version_file(self, document_id, version_number=None):
        raise NotImplementedError

    def list_documents(self, category_id=None, limit=50, offset=0):
        raise NotImplementedError

    def get_document(self, document_id):
        raise NotImplementedError

    def delete_document(self, document_id):
        raise NotImplementedError


def _run_batch(files, service, category_id=None):
    return asyncio.run(
        upload_documents_batch(
            files=files,
            category_id=category_id,
            current_user=_user(),
            document_service=service,
        )
    )


def test_batch_uploads_every_valid_file():
    service = _StubDocumentService()
    result = _run_batch(
        [_upload("a.txt", b"hello"), _upload("b.txt", b"world")], service
    )
    assert result["total"] == 2
    assert result["succeeded"] == 2
    assert result["failed"] == 0
    assert [u["file_name"] for u in service.uploads] == ["a.txt", "b.txt"]
    assert all(item["ok"] for item in result["items"])


def test_batch_infers_image_kind_from_extension():
    service = _StubDocumentService()
    result = _run_batch(
        [_upload("pic.png", _PNG_BYTES), _upload("notes.txt", b"hello")], service
    )
    assert result["succeeded"] == 2
    by_name = {u["file_name"]: u for u in service.uploads}
    assert by_name["pic.png"]["content_type"] == ContentType.FOTO
    assert by_name["notes.txt"]["content_type"] == ContentType.TEXTO


def test_batch_isolates_invalid_files():
    service = _StubDocumentService()
    result = _run_batch(
        [_upload("ok.txt", b"hello"), _upload("virus.exe", b"MZ...")], service
    )
    assert result["succeeded"] == 1
    assert result["failed"] == 1
    failed = next(item for item in result["items"] if not item["ok"])
    assert failed["file_name"] == "virus.exe"
    assert "Unsupported file extension" in failed["error"]
    assert [u["file_name"] for u in service.uploads] == ["ok.txt"]


def test_batch_isolates_ingestion_failures():
    service = _StubDocumentService(fail_names={"bad.txt"})
    result = _run_batch(
        [_upload("bad.txt", b"hello"), _upload("good.txt", b"world")], service
    )
    assert result["succeeded"] == 1
    assert result["failed"] == 1
    failed = next(item for item in result["items"] if not item["ok"])
    assert failed["file_name"] == "bad.txt"


def test_batch_passes_user_and_category_to_service():
    service = _StubDocumentService()
    _run_batch([_upload("a.txt", b"hello")], service, category_id="cat-1")
    assert service.uploads[0]["uploaded_by"] == "u1"
    assert service.uploads[0]["category_id"] == "cat-1"


def test_batch_rejects_empty_and_oversized_batches():
    service = _StubDocumentService()
    with pytest.raises(ValidationError):
        _run_batch([], service)
    with pytest.raises(ValidationError):
        _run_batch([_upload(f"f{i}.txt", b"x") for i in range(21)], service)
    assert service.uploads == []

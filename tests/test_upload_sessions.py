"""Resumable upload sessions: create → chunks (pause/resume) → complete.

The service is exercised directly with the sqlite session from conftest and a
stub DocumentService, so no extraction/embedding runs — `complete` must simply
hand the accumulated bytes to the regular ingestion entry point.
"""

import pytest

from src.enums.content_type import ContentType
from src.enums.document_category import DocumentCategory
from src.enums.upload_session_status import UploadSessionStatus
from src.exceptions import ConflictError, NotFoundError, ValidationError
from src.models.category import Category
from src.models.upload_session import UploadSession
from src.models.user import User
from src.services.upload_session_service import UploadSessionService
from src.services.upload_strategies._shared import MAX_UPLOAD_SIZE


def _seed_user(session, user_id: str) -> str:
    session.add(
        User(id=user_id, name=user_id, email=f"{user_id}@x.com", password_hash="!disabled!")
    )
    session.commit()
    return user_id


def _seed_category(session, category_id: str = "cat-1") -> str:
    session.add(Category(id=category_id, name=category_id, slug=category_id))
    session.commit()
    return category_id


class _StubDocumentService:
    def __init__(self):
        self.uploads: list[dict] = []

    def upload_new_document(
        self,
        file_data,
        content_type,
        file_name,
        category,
        uploaded_by=None,
        category_id=None,
    ):
        self.uploads.append(
            {
                "file_data": file_data,
                "content_type": content_type,
                "file_name": file_name,
                "category": category,
                "uploaded_by": uploaded_by,
                "category_id": category_id,
            }
        )
        return {
            "document_id": "doc-1",
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


@pytest.fixture
def doc_service():
    return _StubDocumentService()


@pytest.fixture
def service(session, doc_service):
    return UploadSessionService(session, doc_service)


@pytest.fixture
def user_id(session):
    return _seed_user(session, "u1")


def test_create_session_starts_active_at_offset_zero(service, user_id):
    out = service.create_session("report.pdf", 10, user_id)
    assert out["status"] == UploadSessionStatus.ACTIVE.value
    assert out["bytes_received"] == 0
    assert out["next_offset"] == 0
    assert out["total_size"] == 10


def test_create_session_rejects_unknown_extension(service, user_id):
    with pytest.raises(ValidationError):
        service.create_session("data.csv", 10, user_id)


def test_create_session_rejects_bad_sizes(service, user_id):
    with pytest.raises(ValidationError):
        service.create_session("a.txt", 0, user_id)
    with pytest.raises(ValidationError):
        service.create_session("a.txt", MAX_UPLOAD_SIZE + 1, user_id)


def test_create_session_rejects_unknown_category(service, user_id):
    with pytest.raises(ValidationError):
        service.create_session("a.txt", 10, user_id, category_id="nope")


def test_create_session_accepts_existing_category(service, session, user_id):
    category_id = _seed_category(session)
    out = service.create_session("a.txt", 10, user_id, category_id=category_id)
    assert out["category_id"] == category_id


def test_append_chunks_advance_offset(service, user_id):
    sid = service.create_session("a.txt", 11, user_id)["id"]
    out = service.append_chunk(sid, user_id, 0, b"hello ")
    assert out["bytes_received"] == 6
    assert out["next_offset"] == 6
    out = service.append_chunk(sid, user_id, 6, b"world")
    assert out["bytes_received"] == 11


def test_append_with_wrong_offset_conflicts_and_reports_position(service, user_id):
    sid = service.create_session("a.txt", 11, user_id)["id"]
    service.append_chunk(sid, user_id, 0, b"hello ")
    with pytest.raises(ConflictError) as exc:
        service.append_chunk(sid, user_id, 0, b"hello ")
    assert "6" in str(exc.value)


def test_append_beyond_declared_size_is_rejected(service, user_id):
    sid = service.create_session("a.txt", 4, user_id)["id"]
    with pytest.raises(ValidationError):
        service.append_chunk(sid, user_id, 0, b"too big")


def test_pause_and_resume_from_reported_offset(service, user_id):
    sid = service.create_session("a.txt", 11, user_id)["id"]
    service.append_chunk(sid, user_id, 0, b"hello ")

    paused = service.pause(sid, user_id)
    assert paused["status"] == UploadSessionStatus.PAUSED.value

    status = service.get_status(sid, user_id)
    assert status["status"] == UploadSessionStatus.PAUSED.value
    assert status["next_offset"] == 6

    out = service.append_chunk(sid, user_id, status["next_offset"], b"world")
    assert out["status"] == UploadSessionStatus.ACTIVE.value
    assert out["bytes_received"] == 11


def test_complete_requires_every_byte(service, user_id):
    sid = service.create_session("a.txt", 11, user_id)["id"]
    service.append_chunk(sid, user_id, 0, b"hello ")
    with pytest.raises(ValidationError):
        service.complete(sid, user_id)


def test_complete_ingests_and_clears_blob(service, session, doc_service, user_id):
    data = b"hello world"
    sid = service.create_session("a.txt", len(data), user_id)["id"]
    service.append_chunk(sid, user_id, 0, data[:6])
    service.append_chunk(sid, user_id, 6, data[6:])

    result = service.complete(sid, user_id)

    assert result["document_id"] == "doc-1"
    upload = doc_service.uploads[0]
    assert upload["file_data"] == data
    assert upload["content_type"] == ContentType.TEXT
    assert upload["category"] == DocumentCategory.TEXT
    assert upload["uploaded_by"] == user_id

    row = session.get(UploadSession, sid)
    assert row.status == UploadSessionStatus.COMPLETED.value
    assert row.data == b""


def test_complete_rejects_mime_mismatch(service, doc_service, user_id):
    data = b"definitely not a pdf, just plain text"
    sid = service.create_session("report.pdf", len(data), user_id)["id"]
    service.append_chunk(sid, user_id, 0, data)
    with pytest.raises(ValidationError):
        service.complete(sid, user_id)
    assert doc_service.uploads == []


def test_completed_session_rejects_chunks_pause_and_recomplete(service, user_id):
    data = b"hello"
    sid = service.create_session("a.txt", len(data), user_id)["id"]
    service.append_chunk(sid, user_id, 0, data)
    service.complete(sid, user_id)

    with pytest.raises(ConflictError):
        service.append_chunk(sid, user_id, len(data), b"x")
    with pytest.raises(ConflictError):
        service.pause(sid, user_id)
    with pytest.raises(ConflictError):
        service.complete(sid, user_id)


def test_failed_ingestion_leaves_session_retriable(service, session, doc_service, user_id):
    def _boom(*args, **kwargs):
        raise ValidationError("No text extracted from uploaded content.")

    doc_service.upload_new_document = _boom
    data = b"hello"
    sid = service.create_session("a.txt", len(data), user_id)["id"]
    service.append_chunk(sid, user_id, 0, data)

    with pytest.raises(ValidationError):
        service.complete(sid, user_id)

    row = session.get(UploadSession, sid)
    assert row.status != UploadSessionStatus.COMPLETED.value
    assert row.data == data


def test_abort_deletes_session(service, session, user_id):
    sid = service.create_session("a.txt", 10, user_id)["id"]
    service.abort(sid, user_id)
    assert session.get(UploadSession, sid) is None
    with pytest.raises(NotFoundError):
        service.get_status(sid, user_id)


def test_sessions_are_private_to_their_owner(service, session, user_id):
    other = _seed_user(session, "u2")
    sid = service.create_session("a.txt", 10, user_id)["id"]
    with pytest.raises(NotFoundError):
        service.get_status(sid, other)
    with pytest.raises(NotFoundError):
        service.append_chunk(sid, other, 0, b"x")
    with pytest.raises(NotFoundError):
        service.abort(sid, other)

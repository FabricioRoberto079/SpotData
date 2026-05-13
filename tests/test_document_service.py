import pytest

from src.enums.content_type import ContentType
from src.enums.document_category import DocumentCategory
from src.exceptions import NotFoundError, ValidationError
from src.interfaces.text_extractor import ITextExtractor
from src.interfaces.vector_index_service import IVectorIndexService
from src.services.document_service import DocumentService


class _StubExtractor(ITextExtractor):
    def __init__(self, text: str = "extracted"):
        self.text = text

    def extract_from_path(self, file_path, content_type):
        return self.text

    def extract_from_bytes(self, data, content_type):
        return self.text


class _StubIndex(IVectorIndexService):
    def __init__(self):
        self.indexed: list[tuple] = []
        self.demoted: list[str] = []
        self.purged: list[str] = []

    def prepare(self, text):
        return ([text, text, text], [[0.0] * 4, [0.0] * 4, [0.0] * 4])

    def commit(self, document_id, version_number, file_name, content_type, chunks, embeddings):
        self.indexed.append((document_id, version_number, chunks[0]))
        return len(chunks)

    def demote_latest(self, document_id):
        self.demoted.append(document_id)

    def purge_document(self, document_id):
        self.purged.append(document_id)

    def search(self, query, n_results=5):
        return []


@pytest.fixture
def doc_service(session):
    return DocumentService(session, _StubExtractor("hello world"), _StubIndex())


def test_create_document(doc_service):
    doc_id = doc_service.create_document("a.txt", DocumentCategory.TEXT)
    assert doc_id
    info = doc_service.get_document(doc_id)
    assert info["file_name"] == "a.txt"
    assert info["versions_count"] == 0


def test_add_version_indexes_and_marks_completed(session):
    extractor = _StubExtractor("payload text")
    index = _StubIndex()
    svc = DocumentService(session, extractor, index)
    doc_id = svc.create_document("a.txt", DocumentCategory.TEXT)

    v = svc.add_version(doc_id, b"raw", ContentType.TEXTO)
    assert v["version_number"] == 1
    assert v["chunk_count"] == 3
    assert v["vectorization_status"] == "completed"
    assert index.indexed == [(doc_id, 1, "payload text")]


def test_add_version_demotes_previous(session):
    index = _StubIndex()
    svc = DocumentService(session, _StubExtractor("t"), index)
    doc_id = svc.create_document("a.txt", DocumentCategory.TEXT)
    svc.add_version(doc_id, b"v1", ContentType.TEXTO)
    svc.add_version(doc_id, b"v2", ContentType.TEXTO)
    info = svc.get_document(doc_id)
    assert info["latest_version"] == 2
    assert info["versions_count"] == 2
    assert index.demoted == [doc_id]


def test_get_missing_doc_raises(doc_service):
    with pytest.raises(NotFoundError):
        doc_service.get_document("does-not-exist")


def test_add_version_to_missing_doc_raises(session):
    svc = DocumentService(session, _StubExtractor("t"), _StubIndex())
    with pytest.raises(NotFoundError):
        svc.add_version("nope", b"x", ContentType.TEXTO)


def test_add_version_with_empty_extracted_text_raises_validation(session):
    svc = DocumentService(session, _StubExtractor(""), _StubIndex())
    doc_id = svc.create_document("a.txt", DocumentCategory.TEXT)
    with pytest.raises(ValidationError):
        svc.add_version(doc_id, b"x", ContentType.TEXTO)


def test_delete_purges_vectors_and_removes_doc(session):
    index = _StubIndex()
    svc = DocumentService(session, _StubExtractor("t"), index)
    doc_id = svc.create_document("a.txt", DocumentCategory.TEXT)
    svc.delete_document(doc_id)
    assert index.purged == [doc_id]
    with pytest.raises(NotFoundError):
        svc.get_document(doc_id)


def test_upload_same_filename_reuses_document_as_new_version(session):
    svc = DocumentService(session, _StubExtractor("t"), _StubIndex())
    first = svc.upload_new_document(
        b"v1", ContentType.TEXTO, "report.txt", DocumentCategory.TEXT, "user-1"
    )
    second = svc.upload_new_document(
        b"v2", ContentType.TEXTO, "report.txt", DocumentCategory.TEXT, "user-1"
    )
    assert first["created"] is True
    assert second["created"] is False
    assert first["document_id"] == second["document_id"]
    assert second["version"]["version_number"] == 2


def test_upload_same_filename_different_users_creates_separate_docs(session):
    svc = DocumentService(session, _StubExtractor("t"), _StubIndex())
    a = svc.upload_new_document(
        b"v1", ContentType.TEXTO, "report.txt", DocumentCategory.TEXT, "user-1"
    )
    b = svc.upload_new_document(
        b"v1", ContentType.TEXTO, "report.txt", DocumentCategory.TEXT, "user-2"
    )
    assert a["document_id"] != b["document_id"]
    assert a["created"] is True
    assert b["created"] is True

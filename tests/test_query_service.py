import pytest

from src.enums.response_status import ResponseStatus
from src.exceptions import NotFoundError, ValidationError
from src.interfaces.vector_index_service import IVectorIndexService
from src.prompts.rag_prompt import RagAnswer
from src.services.query_service import QueryService
from tests.conftest import FakeLlm


class _StubIndex(IVectorIndexService):
    def __init__(self, results=None):
        self._results = results or []

    def index_text(self, document_id, version_number, file_name, content_type, text):
        return 0

    def demote_latest(self, document_id):
        pass

    def purge_document(self, document_id):
        pass

    def search(self, query, n_results=5):
        return self._results


def test_empty_question_raises_validation(session):
    svc = QueryService(session, _StubIndex(), FakeLlm())
    with pytest.raises(ValidationError):
        svc.ask("   ")


def test_ask_with_no_contexts_persists_not_found_status(session):
    svc = QueryService(session, _StubIndex(results=[]), FakeLlm())
    out = svc.ask("alguma pergunta")
    assert out["status"] == ResponseStatus.NOT_FOUND.value
    assert out["citations"] == []


def test_ask_unknown_chat_raises_not_found(session):
    svc = QueryService(session, _StubIndex(), FakeLlm())
    with pytest.raises(NotFoundError):
        svc.ask("oi", chat_id="nao-existe")


def test_ask_success_persists_response(session):
    contexts = [
        {
            "vector_id": "v1",
            "document_id": "doc-1",
            "version_number": 1,
            "chunk_index": 0,
            "file_name": "a.txt",
            "content_type": "texto",
            "distance": 0.1,
            "snippet": "trecho relevante",
        }
    ]
    rag = RagAnswer(
        status=ResponseStatus.SUCCESS.value,
        answer="resposta gerada",
        citations=[],
    )
    svc = QueryService(session, _StubIndex(results=contexts), FakeLlm(rag))
    out = svc.ask("qual é a resposta?")
    assert out["status"] == ResponseStatus.SUCCESS.value
    assert out["answer"] == "resposta gerada"


def test_get_unknown_query_raises_not_found(session):
    with pytest.raises(NotFoundError):
        QueryService(session, _StubIndex(), FakeLlm()).get("nope")

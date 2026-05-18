import pytest

from src.enums.response_status import ResponseStatus
from src.exceptions import NotFoundError, ValidationError
from src.prompts.rag_prompt import RagAnswer
from src.services.chat_service import ChatService
from tests.conftest import FakeLlm, StubQaCache, StubVectorIndex


def test_empty_question_raises_validation(session):
    svc = ChatService(session, StubVectorIndex(), FakeLlm(), StubQaCache())
    with pytest.raises(ValidationError):
        svc.ask("   ")


def test_ask_with_no_contexts_persists_not_found_status(session):
    svc = ChatService(session, StubVectorIndex(results=[]), FakeLlm(), StubQaCache())
    out = svc.ask("alguma pergunta")
    assert out["status"] == ResponseStatus.NOT_FOUND.value
    assert out["citations"] == []


def test_ask_unknown_chat_raises_not_found(session):
    svc = ChatService(session, StubVectorIndex(), FakeLlm(), StubQaCache())
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
    svc = ChatService(session, StubVectorIndex(results=contexts), FakeLlm(rag), StubQaCache())
    out = svc.ask("qual é a resposta?")
    assert out["status"] == ResponseStatus.SUCCESS.value
    assert out["answer"] == "resposta gerada"



import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.enums.response_status import ResponseStatus
from src.exceptions import NotFoundError, ValidationError
from src.integrations.llm import LlmError
from src.models.chat import Chat
from src.models.chat_folder import ChatFolder
from src.models.knowledge_document import KnowledgeDocument
from src.models.query import Query
from src.models.response import Response as ResponseModel
from src.services.chat_service import ChatService
from tests.conftest import FakeLlm, StubQaCache, StubVectorIndex, make_stream_chunks


def _make_service(session):
    return ChatService(session, StubVectorIndex(), FakeLlm(), StubQaCache())


def _run_stream(svc: ChatService, **kwargs) -> list[dict]:
    """Run async ask_stream synchronously and collect all events."""

    async def _consume():
        events: list[dict] = []
        async for event in svc.ask_stream(**kwargs):
            events.append(event)
        return events

    return asyncio.run(_consume())


def _seed_chat(session, title, folder_id=None):
    chat = Chat(title=title, folder_id=folder_id)
    session.add(chat)
    session.commit()
    return chat


def test_get_returns_seeded_chat(session):
    chat = _seed_chat(session, "Meu chat")
    assert _make_service(session).get(chat.id)["title"] == "Meu chat"


def test_list_filters_by_folder(session):
    folder = ChatFolder(id="folder-1", name="F1")
    session.add(folder)
    session.commit()
    a = _seed_chat(session, "A", folder_id=None)
    b = _seed_chat(session, "B", folder_id="folder-1")
    svc = _make_service(session)

    titles_no_filter = sorted(c["title"] for c in svc.list())
    assert titles_no_filter == ["A", "B"]

    only_b = svc.list(folder_id="folder-1")
    assert [c["id"] for c in only_b] == [b.id]
    assert a.id not in [c["id"] for c in only_b]


def test_list_returns_newest_chat_first(session):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    oldest = Chat(title="oldest", created_at=base)
    middle = Chat(title="middle", created_at=base + timedelta(minutes=5))
    newest = Chat(title="newest", created_at=base + timedelta(minutes=10))
    session.add_all([oldest, middle, newest])
    session.commit()

    titles = [c["title"] for c in _make_service(session).list()]
    assert titles == ["newest", "middle", "oldest"]


def test_get_missing_raises_not_found(session):
    with pytest.raises(NotFoundError):
        _make_service(session).get("inexistente")


def test_delete_missing_raises_not_found(session):
    with pytest.raises(NotFoundError):
        _make_service(session).delete("inexistente")


def test_ask_stream_unknown_chat_raises_not_found(session):
    svc = _make_service(session)
    with pytest.raises(NotFoundError):
        _run_stream(svc, question="oi", chat_id="nao-existe")


def test_delete_removes(session):
    chat = _seed_chat(session, "X")
    svc = _make_service(session)
    svc.delete(chat.id)
    with pytest.raises(NotFoundError):
        svc.get(chat.id)


def _contexts():
    return [
        {
            "document_id": "doc-1",
            "version_number": 1,
            "chunk_index": 0,
            "file_name": "a.txt",
            "content_type": "texto",
            "distance": 0.1,
            "snippet": "trecho relevante",
        }
    ]


def test_ask_stream_emits_tokens_and_persists_full_text(session):
    doc = KnowledgeDocument(
        id="doc-1",
        file_name="a.txt",
        category="documents",
    )
    session.add(doc)
    session.commit()
    rag = RagAnswer(
        status="success",
        answer="você vai para a copa",
        citations=[
            Citation(
                document_id="doc-1",
                version_number=1,
                excerpt="trecho relevante",
                confidence_score=0.9,
            )
        ],
    )
    llm = FakeLlm(structured_response=rag)
    svc = ChatService(session, StubVectorIndex(results=_contexts()), llm, StubQaCache())

    events = _run_stream(svc, question="Qual a copa?")

    assert events[0]["type"] == "meta"
    chat_id = events[0]["chat_id"]
    query_id = events[0]["query_id"]
    response_id = events[0]["response_id"]
    assert chat_id and query_id and response_id

    citation_events = [e for e in events if e["type"] == "citation"]
    assert len(citation_events) == 1

    token_payloads = [e["content"] for e in events if e["type"] == "token"]
    assert "".join(token_payloads) == "você vai para a copa"

    final = events[-1]
    assert final["type"] == "done"
    assert final["status"] == ResponseStatus.SUCCESS.value
    assert final["time_ms"] >= 0

    stored = session.get(ResponseModel, response_id)
    assert stored is not None
    assert stored.response_text == "você vai para a copa"
    assert stored.status == ResponseStatus.SUCCESS.value
    assert session.get(Query, query_id).chat_id == chat_id


def test_ask_stream_emits_citation_with_page(session):
    doc = KnowledgeDocument(
        id="doc-stream",
        file_name="manual.pdf",
        category="documents",
    )
    session.add(doc)
    session.commit()

    contexts = [
        {
            "vector_id": "v1",
            "document_id": "doc-stream",
            "version_number": 1,
            "chunk_index": 0,
            "file_name": "manual.pdf",
            "content_type": "pdf",
            "page": 4,
            "distance": 0.1,
            "snippet": "a meta de 2026 é de 12 milhões",
        }
    ]
    chunks = make_stream_chunks(
        answer="A meta de 2026 é de **12 milhões**.",
        citations=[
            {
                "document_id": "doc-stream",
                "version_number": 1,
                "excerpt": "meta de 2026 é de 12 milhões",
                "confidence": 0.92,
            }
        ],
    )
    llm = FakeLlm(stream_chunks=chunks)
    svc = ChatService(session, StubVectorIndex(results=contexts), llm, StubQaCache())

    events = _run_stream(svc, question="Qual a meta de 2026?")

    citation_events = [e for e in events if e["type"] == "citation"]
    assert len(citation_events) == 1
    citation = citation_events[0]["citation"]
    assert citation["document_id"] == "doc-stream"
    assert citation["page"] == 4
    assert citation["excerpt"] == "meta de 2026 é de 12 milhões"

    types = [e["type"] for e in events]
    assert types.index("citation") < types.index("token"), (
        "citation must be emitted before tokens"
    )
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == ResponseStatus.SUCCESS.value


def test_ask_stream_no_contexts_returns_insufficient(session):
    llm = FakeLlm(stream_chunks=[])
    svc = ChatService(session, StubVectorIndex(results=[]), llm, StubQaCache())

    events = _run_stream(svc, question="pergunta sem contexto")

    assert events[0]["type"] == "meta"
    assert [e for e in events if e["type"] == "token"] == []
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == ResponseStatus.INSUFFICIENT_INFORMATION.value


def test_ask_stream_low_confidence_returns_insufficient(session):
    """Quando o LLM responde success mas todas as citations têm confidence_score < 0.5,
    o backend trata como insufficient_information (LLM 'sabe que está chutando')."""
    doc = KnowledgeDocument(
        id="doc-low",
        file_name="x.pdf",
        category="documents",
    )
    session.add(doc)
    session.commit()

    contexts = [
        {
            "vector_id": "v1",
            "document_id": "doc-low",
            "version_number": 1,
            "chunk_index": 0,
            "file_name": "x.pdf",
            "content_type": "pdf",
            "distance": 0.1,
            "snippet": "snippet qualquer",
        }
    ]
    chunks = make_stream_chunks(
        answer="resposta com baixa fundamentação",
        citations=[
            {
                "document_id": "doc-low",
                "version_number": 1,
                "excerpt": "snippet qualquer",
                "confidence": 0.3,
            }
        ],
    )
    llm = FakeLlm(stream_chunks=chunks)
    svc = ChatService(session, StubVectorIndex(results=contexts), llm, StubQaCache())

    events = _run_stream(svc, question="Pergunta de baixa confiança?")

    assert [e for e in events if e["type"] == "token"] == []
    assert [e for e in events if e["type"] == "citation"] == []
    assert events[-1]["status"] == ResponseStatus.INSUFFICIENT_INFORMATION.value


def test_ask_stream_insufficient_when_llm_returns_no_citations(session):
    """For chitchat ("oi") the LLM emits no Cite calls and (per the system prompt)
    no prose — backend marks the answer as insufficient_information."""
    llm = FakeLlm(stream_chunks=make_stream_chunks(answer="", citations=[]))
    svc = ChatService(session, StubVectorIndex(results=_contexts()), llm, StubQaCache())

    events = _run_stream(svc, question="oi")

    assert [e for e in events if e["type"] == "token"] == []
    assert [e for e in events if e["type"] == "citation"] == []
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == ResponseStatus.INSUFFICIENT_INFORMATION.value


def test_ask_stream_propagates_llm_error_and_marks_response(session):
    err = LlmError("rate_limit", 429, "slow down")
    llm = FakeLlm(stream_error=err)
    svc = ChatService(session, StubVectorIndex(results=_contexts()), llm, StubQaCache())

    events = _run_stream(svc, question="qual a meta?")

    assert events[0]["type"] == "meta"
    response_id = events[0]["response_id"]
    error_event = events[-1]
    assert error_event["type"] == "error"
    assert error_event["kind"] == "rate_limit"
    assert error_event["message"] == "slow down"

    stored = session.get(ResponseModel, response_id)
    assert stored.status == ResponseStatus.ERROR.value
    assert "rate_limit" in stored.response_text


def test_ask_stream_serves_from_cache_emits_citations_before_tokens(session):
    doc = KnowledgeDocument(
        id="doc-cache",
        file_name="manual.pdf",
        category="documents",
    )
    session.add(doc)
    session.commit()

    cache = StubQaCache()
    cache.store[
        __import__("src.interfaces.qa_cache", fromlist=["question_key"]).question_key(
            "Qual a meta?"
        )
    ] = {
        "question": "Qual a meta?",
        "answer": "A meta é de 12 milhões.",
        "status": ResponseStatus.SUCCESS.value,
        "citations": [
            {
                "document_id": "doc-cache",
                "version_number": 1,
                "excerpt": "meta de 12 milhões",
                "confidence_score": 0.95,
                "page": 3,
            }
        ],
    }

    llm = FakeLlm(stream_chunks=[])  # cache hit → LLM stream is never invoked
    svc = ChatService(session, StubVectorIndex(results=[]), llm, cache)

    events = _run_stream(svc, question="Qual a meta?")

    types = [e["type"] for e in events]
    assert types[0] == "meta"
    first_citation_idx = types.index("citation")
    first_token_idx = types.index("token")
    assert first_citation_idx < first_token_idx, "citations must come before tokens for cache hits"

    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "A meta é de 12 milhões."
    citation_events = [e for e in events if e["type"] == "citation"]
    assert len(citation_events) == 1
    assert citation_events[0]["citation"]["page"] == 3
    assert events[-1]["type"] == "done"
    assert llm.embed_calls == []  # cache hit on L1 → no embedding generated either


def test_ask_stream_rejects_empty_question(session):
    svc = ChatService(session, StubVectorIndex(), FakeLlm(), StubQaCache())
    with pytest.raises(ValidationError):
        _run_stream(svc, question="   ")

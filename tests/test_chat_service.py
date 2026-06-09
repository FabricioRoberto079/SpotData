import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.enums.response_status import ResponseStatus
from src.exceptions import NotFoundError, ValidationError
from src.integrations.llm import LlmError
from src.models.category import Category
from src.models.chat import Chat
from src.models.chat_folder import ChatFolder
from src.models.knowledge_document import KnowledgeDocument
from src.models.query import Query
from src.models.response import Response as ResponseModel
from src.services.chat_service import ChatService
from tests.conftest import FakeLlm, StubQaCache, StubVectorIndex, make_structured_partials


def _make_service(session):
    return ChatService(session, StubVectorIndex(), FakeLlm(), StubQaCache())


def _run_stream(svc: ChatService, **kwargs) -> list[dict]:
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

    partials = make_structured_partials(
        answer="você vai para a copa",
        citations=[{"context_index": 0, "confidence": 0.9}],
    )
    llm = FakeLlm(structured_partials=partials)
    svc = ChatService(session, StubVectorIndex(results=_contexts()), llm, StubQaCache())

    events = _run_stream(svc, question="Qual a copa?")

    assert events[0]["type"] == "meta"
    chat_id = events[0]["chat_id"]
    query_id = events[0]["query_id"]
    response_id = events[0]["response_id"]
    assert chat_id and query_id and response_id

    citation_events = [e for e in events if e["type"] == "citations"]
    assert len(citation_events) == 1
    assert len(citation_events[0]["citations"]) == 1

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


def test_ask_stream_new_chat_scopes_search_to_chosen_category(session):
    session.add(Category(id="cat-rh", name="RH", slug="rh"))
    session.add(KnowledgeDocument(id="doc-1", file_name="a.txt", category="documents"))
    session.commit()

    partials = make_structured_partials(
        answer="resposta",
        citations=[{"context_index": 0, "confidence": 0.9}],
    )
    index = StubVectorIndex(results=_contexts())
    svc = ChatService(session, index, FakeLlm(structured_partials=partials), StubQaCache())

    events = _run_stream(svc, question="Qual a copa?", category_id="cat-rh")
    chat_id = events[0]["chat_id"]

    # the chosen category is stored on the chat and used to scope retrieval
    assert session.get(Chat, chat_id).category_id == "cat-rh"
    assert index.last_search_scope == "cat-rh"

    # a follow-up on the same chat reuses its category without re-sending it
    _run_stream(svc, question="E agora?", chat_id=chat_id)
    assert index.last_search_scope == "cat-rh"


def test_ask_stream_categoryless_chat_searches_every_category(session):
    session.add(KnowledgeDocument(id="doc-1", file_name="a.txt", category="documents"))
    session.commit()

    partials = make_structured_partials(
        answer="resposta",
        citations=[{"context_index": 0, "confidence": 0.9}],
    )
    index = StubVectorIndex(results=_contexts())
    svc = ChatService(session, index, FakeLlm(structured_partials=partials), StubQaCache())

    events = _run_stream(svc, question="Qual a copa?")
    chat_id = events[0]["chat_id"]

    assert session.get(Chat, chat_id).category_id is None
    assert index.last_search_scope is None


def test_ask_stream_unknown_category_raises_validation(session):
    svc = _make_service(session)
    with pytest.raises(ValidationError):
        _run_stream(svc, question="oi", category_id="ghost-cat")


def test_ask_stream_emits_citations_before_tokens_with_page(session):
    doc = KnowledgeDocument(
        id="doc-stream",
        file_name="manual.pdf",
        category="documents",
    )
    session.add(doc)
    session.commit()

    contexts = [
        {
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
    partials = make_structured_partials(
        answer="A meta de 2026 é de **12 milhões**.",
        citations=[{"context_index": 0, "confidence": 0.92}],
    )
    llm = FakeLlm(structured_partials=partials)
    svc = ChatService(session, StubVectorIndex(results=contexts), llm, StubQaCache())

    events = _run_stream(svc, question="Qual a meta de 2026?")

    citation_events = [e for e in events if e["type"] == "citations"]
    assert len(citation_events) == 1
    citations = citation_events[0]["citations"]
    assert len(citations) == 1
    c = citations[0]
    assert c["document_id"] == "doc-stream"
    assert c["page"] == 4
    assert c["excerpt"] == "a meta de 2026 é de 12 milhões"
    assert c["confidence_score"] == 0.92

    types = [e["type"] for e in events]
    assert types.index("citations") < types.index("token"), (
        "citations event must be emitted before tokens"
    )
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == ResponseStatus.SUCCESS.value


def test_ask_stream_no_contexts_returns_insufficient(session):
    llm = FakeLlm()
    svc = ChatService(session, StubVectorIndex(results=[]), llm, StubQaCache())

    events = _run_stream(svc, question="pergunta sem contexto")

    assert events[0]["type"] == "meta"
    assert [e for e in events if e["type"] == "token"] == []
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == ResponseStatus.INSUFFICIENT_INFORMATION.value


def test_ask_stream_low_confidence_returns_insufficient(session):
    doc = KnowledgeDocument(
        id="doc-low",
        file_name="x.pdf",
        category="documents",
    )
    session.add(doc)
    session.commit()

    contexts = [
        {
            "document_id": "doc-low",
            "version_number": 1,
            "chunk_index": 0,
            "file_name": "x.pdf",
            "content_type": "pdf",
            "distance": 0.1,
            "snippet": "snippet qualquer",
        }
    ]
    partials = make_structured_partials(
        answer="resposta com baixa fundamentação",
        citations=[{"context_index": 0, "confidence": 0.4}],
    )
    llm = FakeLlm(structured_partials=partials)
    svc = ChatService(session, StubVectorIndex(results=contexts), llm, StubQaCache())

    events = _run_stream(svc, question="Pergunta de baixa confiança?")

    assert [e for e in events if e["type"] == "token"] == []
    assert [e for e in events if e["type"] == "citations"] == [
        {"type": "citations", "citations": []}
    ]
    assert events[-1]["status"] == ResponseStatus.INSUFFICIENT_INFORMATION.value


def test_ask_stream_insufficient_when_llm_returns_no_citations(session):
    partials = make_structured_partials(answer="", citations=[])
    llm = FakeLlm(structured_partials=partials)
    svc = ChatService(session, StubVectorIndex(results=_contexts()), llm, StubQaCache())

    events = _run_stream(svc, question="oi")

    assert [e for e in events if e["type"] == "token"] == []
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
    assert llm.embed_calls == [["qual a meta?"]]


def test_ask_stream_serves_from_cache_emits_citations_before_tokens(session):
    from src.interfaces.qa_cache import question_key

    doc = KnowledgeDocument(
        id="doc-cache",
        file_name="manual.pdf",
        category="documents",
    )
    session.add(doc)
    session.commit()

    cache = StubQaCache()
    cache.store[question_key("Qual a meta?")] = {
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

    llm = FakeLlm(structured_partials=[])
    svc = ChatService(session, StubVectorIndex(results=[]), llm, cache)

    events = _run_stream(svc, question="Qual a meta?")

    types = [e["type"] for e in events]
    assert types[0] == "meta"
    first_citations_idx = types.index("citations")
    first_token_idx = types.index("token")
    assert first_citations_idx < first_token_idx, (
        "citations must come before tokens for cache hits"
    )

    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "A meta é de 12 milhões."
    citation_events = [e for e in events if e["type"] == "citations"]
    assert len(citation_events) == 1
    assert len(citation_events[0]["citations"]) == 1
    assert citation_events[0]["citations"][0]["page"] == 3
    assert events[-1]["type"] == "done"
    assert llm.embed_calls == []


def test_ask_stream_cache_is_scoped_by_category(session):
    from src.interfaces.qa_cache import question_key

    session.add_all(
        [
            Category(id="cat-1", name="cat-1", slug="cat-1"),
            Category(id="cat-2", name="cat-2", slug="cat-2"),
            KnowledgeDocument(
                id="doc-cache", file_name="manual.pdf", category="documents"
            ),
        ]
    )
    session.commit()

    answer = "A meta é de 12 milhões."
    cache = StubQaCache()
    cache.store[question_key("Qual a meta?", "cat-1")] = {
        "question": "Qual a meta?",
        "answer": answer,
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

    # Empty retrieval, so a real (non-cached) run could never produce the answer
    # below — only a same-scope cache hit can.
    svc = ChatService(session, StubVectorIndex(results=[]), FakeLlm(), cache)

    same_scope = _run_stream(svc, question="Qual a meta?", category_id="cat-1")
    served = "".join(e["content"] for e in same_scope if e["type"] == "token")
    assert served == answer

    # A different category must never read back cat-1's cached answer.
    other_scope = _run_stream(svc, question="Qual a meta?", category_id="cat-2")
    leaked = "".join(e["content"] for e in other_scope if e["type"] == "token")
    assert leaked != answer


def test_ask_stream_rejects_empty_question(session):
    svc = ChatService(session, StubVectorIndex(), FakeLlm(), StubQaCache())
    with pytest.raises(ValidationError):
        _run_stream(svc, question="   ")

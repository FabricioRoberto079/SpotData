import pytest

from src.enums.response_status import ResponseStatus
from src.exceptions import NotFoundError
from src.models.chat import Chat
from src.prompts.rag_prompt import RagAnswer
from src.services.chat_service import ChatService
from tests.conftest import FakeLlm, StubQaCache, StubVectorIndex


def _make_service(session):
    return ChatService(session, StubVectorIndex(), FakeLlm(), StubQaCache())


def _seed_chat(session, title, folder_id=None):
    chat = Chat(title=title, folder_id=folder_id)
    session.add(chat)
    session.commit()
    return chat


def test_get_returns_seeded_chat(session):
    chat = _seed_chat(session, "Meu chat")
    assert _make_service(session).get(chat.id)["title"] == "Meu chat"


def test_list_filters_by_folder(session):
    a = _seed_chat(session, "A", folder_id=None)
    b = _seed_chat(session, "B", folder_id="folder-1")
    svc = _make_service(session)

    titles_no_filter = sorted(c["title"] for c in svc.list())
    assert titles_no_filter == ["A", "B"]

    only_b = svc.list(folder_id="folder-1")
    assert [c["id"] for c in only_b] == [b.id]
    assert a.id not in [c["id"] for c in only_b]


def test_get_missing_raises_not_found(session):
    with pytest.raises(NotFoundError):
        _make_service(session).get("inexistente")


def test_delete_missing_raises_not_found(session):
    with pytest.raises(NotFoundError):
        _make_service(session).delete("inexistente")


def test_delete_removes(session):
    chat = _seed_chat(session, "X")
    svc = _make_service(session)
    svc.delete(chat.id)
    with pytest.raises(NotFoundError):
        svc.get(chat.id)


def _contexts():
    return [
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


def test_cache_hit_bypasses_llm(session):
    rag = RagAnswer(
        status=ResponseStatus.SUCCESS.value,
        answer="resposta cacheada",
        citations=[],
    )
    llm = FakeLlm(rag)
    cache = StubQaCache()
    svc = ChatService(session, StubVectorIndex(results=_contexts()), llm, cache)

    first = svc.ask("Qual é a meta?")
    assert first["answer"] == "resposta cacheada"
    assert len(cache.store) == 1

    llm.structured_response = None
    second = svc.ask("  QUAL é A meta?  ")
    assert second["answer"] == "resposta cacheada"
    assert second["query_id"] != first["query_id"]


def test_cache_skipped_when_chat_id_passed(session):
    rag = RagAnswer(
        status=ResponseStatus.SUCCESS.value,
        answer="primeira",
        citations=[],
    )
    cache = StubQaCache()
    svc = ChatService(session, StubVectorIndex(results=_contexts()), FakeLlm(rag), cache)

    first = svc.ask("Qual é a meta?")
    assert len(cache.store) == 1

    rag2 = RagAnswer(
        status=ResponseStatus.SUCCESS.value,
        answer="segunda",
        citations=[],
    )
    svc2 = ChatService(
        session, StubVectorIndex(results=_contexts()), FakeLlm(rag2), cache
    )
    out = svc2.ask("Qual é a meta?", chat_id=first["chat_id"])
    assert out["answer"] == "segunda"


def test_cache_skips_storage_when_status_not_success(session):
    rag = RagAnswer(
        status="insufficient_information",
        answer="não sei",
        citations=[],
    )
    cache = StubQaCache()
    svc = ChatService(session, StubVectorIndex(results=_contexts()), FakeLlm(rag), cache)
    svc.ask("uma pergunta qualquer")
    assert cache.store == {}

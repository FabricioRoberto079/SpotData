import pytest

from src.exceptions import NotFoundError
from src.models.chat import Chat
from src.services.chat_service import ChatService
from tests.conftest import FakeLlm, StubVectorIndex


def _make_service(session):
    return ChatService(session, StubVectorIndex(), FakeLlm())


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

import pytest

from src.exceptions import NotFoundError
from src.services.chat_service import ChatService


def test_create_and_get(session):
    svc = ChatService(session)
    created = svc.create("Meu chat")
    assert created["title"] == "Meu chat"
    assert svc.get(created["id"])["title"] == "Meu chat"


def test_list_filters_by_folder(session):
    svc = ChatService(session)
    a = svc.create("A", folder_id=None)
    b = svc.create("B", folder_id="folder-1")
    titles_no_filter = sorted(c["title"] for c in svc.list())
    assert titles_no_filter == ["A", "B"]
    only_b = svc.list(folder_id="folder-1")
    assert [c["id"] for c in only_b] == [b["id"]]
    assert a["id"] not in [c["id"] for c in only_b]


def test_get_missing_raises_not_found(session):
    with pytest.raises(NotFoundError):
        ChatService(session).get("inexistente")


def test_delete_missing_raises_not_found(session):
    with pytest.raises(NotFoundError):
        ChatService(session).delete("inexistente")


def test_delete_removes(session):
    svc = ChatService(session)
    chat = svc.create("X")
    svc.delete(chat["id"])
    with pytest.raises(NotFoundError):
        svc.get(chat["id"])

import pytest

from src.exceptions import ConflictError, NotFoundError
from src.services.folder_service import ChatFolderService, DocumentFolderService


def test_create_and_list_tree(session):
    svc = DocumentFolderService(session)
    root = svc.create("Root")
    child = svc.create("Child", parent_id=root["id"])
    tree = svc.list_tree()
    assert len(tree) == 1
    assert tree[0]["id"] == root["id"]
    assert tree[0]["children"][0]["id"] == child["id"]


def test_create_with_unknown_parent_raises_not_found(session):
    with pytest.raises(NotFoundError):
        DocumentFolderService(session).create("X", parent_id="nope")


def test_rename(session):
    svc = DocumentFolderService(session)
    f = svc.create("Old")
    renamed = svc.rename(f["id"], "New")
    assert renamed["name"] == "New"


def test_move_to_self_raises_conflict(session):
    svc = DocumentFolderService(session)
    f = svc.create("X")
    with pytest.raises(ConflictError):
        svc.move(f["id"], new_parent_id=f["id"])


def test_move_to_descendant_raises_conflict(session):
    svc = DocumentFolderService(session)
    a = svc.create("A")
    b = svc.create("B", parent_id=a["id"])
    with pytest.raises(ConflictError):
        svc.move(a["id"], new_parent_id=b["id"])


def test_delete_with_subfolders_raises_conflict(session):
    svc = DocumentFolderService(session)
    a = svc.create("A")
    svc.create("B", parent_id=a["id"])
    with pytest.raises(ConflictError):
        svc.delete(a["id"])


def test_chat_folder_service_works_independently(session):
    doc = DocumentFolderService(session).create("docs")
    chat = ChatFolderService(session).create("chats")
    assert doc["id"] != chat["id"]
    assert len(DocumentFolderService(session).list_tree()) == 1
    assert len(ChatFolderService(session).list_tree()) == 1

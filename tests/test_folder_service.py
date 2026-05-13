import pytest

from src.exceptions import ConflictError, NotFoundError
from src.services.folder_service import ChatFolderService


def test_create_and_list_tree(session):
    svc = ChatFolderService(session)
    root = svc.create("Root")
    child = svc.create("Child", parent_id=root["id"])
    tree = svc.list_tree()
    assert len(tree) == 1
    assert tree[0]["id"] == root["id"]
    assert tree[0]["children"][0]["id"] == child["id"]


def test_create_with_unknown_parent_raises_not_found(session):
    with pytest.raises(NotFoundError):
        ChatFolderService(session).create("X", parent_id="nope")


def test_update_rename(session):
    svc = ChatFolderService(session)
    f = svc.create("Old")
    renamed = svc.update(f["id"], {"name": "New"})
    assert renamed["name"] == "New"


def test_update_move(session):
    svc = ChatFolderService(session)
    a = svc.create("A")
    b = svc.create("B")
    moved = svc.update(b["id"], {"parent_id": a["id"]})
    assert moved["parent_id"] == a["id"]


def test_update_rename_and_move_together(session):
    svc = ChatFolderService(session)
    a = svc.create("A")
    b = svc.create("B")
    result = svc.update(b["id"], {"name": "B-new", "parent_id": a["id"]})
    assert result["name"] == "B-new"
    assert result["parent_id"] == a["id"]


def test_update_move_to_root(session):
    svc = ChatFolderService(session)
    a = svc.create("A")
    b = svc.create("B", parent_id=a["id"])
    moved = svc.update(b["id"], {"parent_id": None})
    assert moved["parent_id"] is None


def test_update_move_to_self_raises_conflict(session):
    svc = ChatFolderService(session)
    f = svc.create("X")
    with pytest.raises(ConflictError):
        svc.update(f["id"], {"parent_id": f["id"]})


def test_update_move_to_descendant_raises_conflict(session):
    svc = ChatFolderService(session)
    a = svc.create("A")
    b = svc.create("B", parent_id=a["id"])
    with pytest.raises(ConflictError):
        svc.update(a["id"], {"parent_id": b["id"]})


def test_delete_with_subfolders_raises_conflict(session):
    svc = ChatFolderService(session)
    a = svc.create("A")
    svc.create("B", parent_id=a["id"])
    with pytest.raises(ConflictError):
        svc.delete(a["id"])

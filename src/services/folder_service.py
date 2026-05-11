from typing import Type

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.data.postgres_client import get_session
from src.exceptions import ConflictError, NotFoundError
from src.interfaces.folder_service import IFolderService
from src.models.chat_folder import ChatFolder
from src.models.document_folder import DocumentFolder

FolderModel = Type[DocumentFolder] | Type[ChatFolder]


class BaseFolderService(IFolderService):
    _model: FolderModel
    _items_attr: str

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _serialize(folder) -> dict:
        return {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "owner_id": folder.owner_id,
            "created_at": folder.created_at.isoformat() if folder.created_at else None,
        }

    @classmethod
    def _build_tree(cls, folders: list) -> list[dict]:
        by_id = {f.id: {**cls._serialize(f), "children": []} for f in folders}
        roots = []
        for f in folders:
            node = by_id[f.id]
            if f.parent_id and f.parent_id in by_id:
                by_id[f.parent_id]["children"].append(node)
            else:
                roots.append(node)
        return roots

    def _ensure_parent_exists(self, parent_id: str | None) -> None:
        if parent_id is None:
            return
        if self._session.get(self._model, parent_id) is None:
            raise NotFoundError(f"Parent folder not found: {parent_id}")

    def _is_descendant(self, candidate_id: str, ancestor_id: str) -> bool:
        current = self._session.get(self._model, candidate_id)
        while current is not None:
            if current.id == ancestor_id:
                return True
            if current.parent_id is None:
                return False
            current = self._session.get(self._model, current.parent_id)
        return False

    def create(
        self,
        name: str,
        parent_id: str | None = None,
        owner_id: str | None = None,
    ) -> dict:
        try:
            self._ensure_parent_exists(parent_id)
            folder = self._model(name=name, parent_id=parent_id, owner_id=owner_id)
            self._session.add(folder)
            self._session.commit()
            self._session.refresh(folder)
            return self._serialize(folder)
        except Exception:
            self._session.rollback()
            raise

    def list_tree(self, owner_id: str | None = None) -> list[dict]:
        stmt = select(self._model)
        if owner_id is not None:
            stmt = stmt.where(self._model.owner_id == owner_id)
        folders = self._session.execute(stmt).scalars().all()
        return self._build_tree(folders)

    def rename(self, folder_id: str, name: str) -> dict:
        try:
            folder = self._session.get(self._model, folder_id)
            if folder is None:
                raise NotFoundError(f"Folder not found: {folder_id}")
            folder.name = name
            self._session.commit()
            self._session.refresh(folder)
            return self._serialize(folder)
        except Exception:
            self._session.rollback()
            raise

    def move(self, folder_id: str, new_parent_id: str | None) -> dict:
        try:
            folder = self._session.get(self._model, folder_id)
            if folder is None:
                raise NotFoundError(f"Folder not found: {folder_id}")
            if new_parent_id == folder_id:
                raise ConflictError(
                    "Cannot move a folder into itself."
                )
            if new_parent_id is not None:
                self._ensure_parent_exists(new_parent_id)
                if self._is_descendant(new_parent_id, folder_id):
                    raise ConflictError(
                        "Cannot move into a descendant (would create a cycle)."
                    )
            folder.parent_id = new_parent_id
            self._session.commit()
            self._session.refresh(folder)
            return self._serialize(folder)
        except Exception:
            self._session.rollback()
            raise

    def delete(self, folder_id: str) -> None:
        try:
            folder = self._session.get(self._model, folder_id)
            if folder is None:
                raise NotFoundError(f"Folder not found: {folder_id}")
            children = (
                self._session.execute(
                    select(self._model).where(self._model.parent_id == folder_id)
                )
                .scalars()
                .all()
            )
            if children:
                raise ConflictError("Folder has subfolders. Remove them first.")

            items = getattr(folder, self._items_attr)
            if items:
                raise ConflictError(
                    f"Folder has {self._items_attr}. Remove them first."
                )

            self._session.delete(folder)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise


class DocumentFolderService(BaseFolderService):
    _model = DocumentFolder
    _items_attr = "documents"


class ChatFolderService(BaseFolderService):
    _model = ChatFolder
    _items_attr = "chats"


def get_document_folder_service(
    session: Session = Depends(get_session),
) -> IFolderService:
    return DocumentFolderService(session)


def get_chat_folder_service(
    session: Session = Depends(get_session),
) -> IFolderService:
    return ChatFolderService(session)

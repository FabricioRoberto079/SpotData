from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.data.postgres_client import get_session
from src.exceptions import ConflictError, NotFoundError
from src.interfaces.folder_service import IFolderService
from src.models.chat_folder import ChatFolder


class ChatFolderService(IFolderService):
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _serialize(folder: ChatFolder) -> dict:
        return {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "owner_id": folder.owner_id,
            "created_at": folder.created_at.isoformat() if folder.created_at else None,
        }

    @classmethod
    def _build_tree(cls, folders: list[ChatFolder]) -> list[dict]:
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
        if self._session.get(ChatFolder, parent_id) is None:
            raise NotFoundError(f"Parent folder not found: {parent_id}")

    def _is_descendant(self, candidate_id: str, ancestor_id: str) -> bool:
        current = self._session.get(ChatFolder, candidate_id)
        while current is not None:
            if current.id == ancestor_id:
                return True
            if current.parent_id is None:
                return False
            current = self._session.get(ChatFolder, current.parent_id)
        return False

    def create(
        self,
        name: str,
        parent_id: str | None = None,
        owner_id: str | None = None,
    ) -> dict:
        try:
            self._ensure_parent_exists(parent_id)
            folder = ChatFolder(name=name, parent_id=parent_id, owner_id=owner_id)
            self._session.add(folder)
            self._session.commit()
            self._session.refresh(folder)
            return self._serialize(folder)
        except Exception:
            self._session.rollback()
            raise

    def list_tree(self, owner_id: str | None = None) -> list[dict]:
        stmt = select(ChatFolder)
        if owner_id is not None:
            stmt = stmt.where(ChatFolder.owner_id == owner_id)
        folders = self._session.execute(stmt).scalars().all()
        return self._build_tree(folders)

    def update(self, folder_id: str, fields: dict) -> dict:
        try:
            folder = self._session.get(ChatFolder, folder_id)
            if folder is None:
                raise NotFoundError(f"Folder not found: {folder_id}")

            if "name" in fields and fields["name"] is not None:
                folder.name = fields["name"]

            if "parent_id" in fields:
                new_parent_id = fields["parent_id"]
                if new_parent_id == folder_id:
                    raise ConflictError("Cannot move a folder into itself.")
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
            folder = self._session.get(ChatFolder, folder_id)
            if folder is None:
                raise NotFoundError(f"Folder not found: {folder_id}")
            children = (
                self._session.execute(
                    select(ChatFolder).where(ChatFolder.parent_id == folder_id)
                )
                .scalars()
                .all()
            )
            if children:
                raise ConflictError("Folder has subfolders. Remove them first.")
            if folder.chats:
                raise ConflictError("Folder has chats. Remove them first.")

            self._session.delete(folder)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise


def get_chat_folder_service(
    session: Session = Depends(get_session),
) -> IFolderService:
    return ChatFolderService(session)

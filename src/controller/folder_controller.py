from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.integrations.auth import get_current_user
from src.interfaces.folder_service import IFolderService
from src.models.user import User
from src.schemas.folder import FolderNode, FolderOut
from src.schemas.system import MessageResponse
from src.services.folder_service import (
    get_chat_folder_service,
    get_document_folder_service,
)


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: str | None = None


class FolderRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class FolderMove(BaseModel):
    parent_id: str | None = None


def _build_router(prefix: str, tag: str, get_service):
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.post("", response_model=FolderOut, summary=f"Create folder under {prefix}")
    async def create_folder(
        payload: FolderCreate,
        current_user: User | None = Depends(get_current_user),
        folder_service: IFolderService = Depends(get_service),
    ):
        owner_id = current_user.id if current_user else None
        return folder_service.create(payload.name, payload.parent_id, owner_id)

    @router.get("", response_model=list[FolderNode], summary=f"List folder tree under {prefix}")
    async def list_folders(
        current_user: User | None = Depends(get_current_user),
        folder_service: IFolderService = Depends(get_service),
    ):
        owner_filter = current_user.id if current_user else None
        return folder_service.list_tree(owner_filter)

    @router.patch(
        "/{folder_id}/rename",
        response_model=FolderOut,
        summary=f"Rename folder under {prefix}",
    )
    async def rename_folder(
        folder_id: str,
        payload: FolderRename,
        current_user: User | None = Depends(get_current_user),
        folder_service: IFolderService = Depends(get_service),
    ):
        return folder_service.rename(folder_id, payload.name)

    @router.patch(
        "/{folder_id}/move",
        response_model=FolderOut,
        summary=f"Move folder under {prefix}",
    )
    async def move_folder(
        folder_id: str,
        payload: FolderMove,
        current_user: User | None = Depends(get_current_user),
        folder_service: IFolderService = Depends(get_service),
    ):
        return folder_service.move(folder_id, payload.parent_id)

    @router.delete(
        "/{folder_id}",
        response_model=MessageResponse,
        summary=f"Delete folder under {prefix}",
    )
    async def delete_folder(
        folder_id: str,
        current_user: User | None = Depends(get_current_user),
        folder_service: IFolderService = Depends(get_service),
    ):
        folder_service.delete(folder_id)
        return {"message": "Folder removed."}

    return router


document_folder_router = _build_router(
    "/document-folders", "document-folders", get_document_folder_service
)
chat_folder_router = _build_router(
    "/chat-folders", "chat-folders", get_chat_folder_service
)

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.integrations.auth import get_current_user
from src.interfaces.folder_service import IFolderService
from src.models.user import User
from src.schemas.folder import FolderNode, FolderOut
from src.schemas.system import MessageResponse
from src.services.folder_service import get_chat_folder_service


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: str | None = None


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: str | None = None


chat_folder_router = APIRouter(prefix="/chat-folders", tags=["chat-folders"])


@chat_folder_router.post("", response_model=FolderOut, summary="Create chat folder")
async def create_folder(
    payload: FolderCreate,
    current_user: User | None = Depends(get_current_user),
    folder_service: IFolderService = Depends(get_chat_folder_service),
):
    owner_id = current_user.id if current_user else None
    return folder_service.create(payload.name, payload.parent_id, owner_id)


@chat_folder_router.get(
    "", response_model=list[FolderNode], summary="List chat folder tree"
)
async def list_folders(
    current_user: User | None = Depends(get_current_user),
    folder_service: IFolderService = Depends(get_chat_folder_service),
):
    owner_filter = current_user.id if current_user else None
    return folder_service.list_tree(owner_filter)


@chat_folder_router.put(
    "/{folder_id}",
    response_model=FolderOut,
    summary="Update chat folder (rename and/or move)",
)
async def update_folder(
    folder_id: str,
    payload: FolderUpdate,
    current_user: User | None = Depends(get_current_user),
    folder_service: IFolderService = Depends(get_chat_folder_service),
):
    return folder_service.update(folder_id, payload.model_dump(exclude_unset=True))


@chat_folder_router.delete(
    "/{folder_id}", response_model=MessageResponse, summary="Delete chat folder"
)
async def delete_folder(
    folder_id: str,
    current_user: User | None = Depends(get_current_user),
    folder_service: IFolderService = Depends(get_chat_folder_service),
):
    folder_service.delete(folder_id)
    return {"message": "Folder removed."}

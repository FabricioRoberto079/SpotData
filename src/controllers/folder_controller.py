from fastapi import APIRouter, Depends

from src.auth import require_user
from src.models.user import User
from src.schemas.folder import FolderCreate, FolderNode, FolderOut, FolderUpdate
from src.schemas.system import MessageResponse
from src.services.folder_service import ChatFolderService, get_chat_folder_service

chat_folder_router = APIRouter(prefix="/chat-folders", tags=["chat-folders"])


@chat_folder_router.post("", response_model=FolderOut, summary="Create chat folder")
async def create_folder(
    payload: FolderCreate,
    current_user: User = Depends(require_user),
    folder_service: ChatFolderService = Depends(get_chat_folder_service),
):
    return folder_service.create(payload.name, payload.parent_id, current_user.id)


@chat_folder_router.get("", response_model=list[FolderNode], summary="List chat folder tree")
async def list_folders(
    current_user: User = Depends(require_user),
    folder_service: ChatFolderService = Depends(get_chat_folder_service),
):
    return folder_service.list_tree(current_user.id)


@chat_folder_router.put(
    "/{folder_id}",
    response_model=FolderOut,
    summary="Update chat folder (rename and/or move)",
)
async def update_folder(
    folder_id: str,
    payload: FolderUpdate,
    current_user: User = Depends(require_user),
    folder_service: ChatFolderService = Depends(get_chat_folder_service),
):
    return folder_service.update(
        folder_id, payload.model_dump(exclude_unset=True), owner_id=current_user.id
    )


@chat_folder_router.delete(
    "/{folder_id}", response_model=MessageResponse, summary="Delete chat folder"
)
async def delete_folder(
    folder_id: str,
    current_user: User = Depends(require_user),
    folder_service: ChatFolderService = Depends(get_chat_folder_service),
):
    folder_service.delete(folder_id, owner_id=current_user.id)
    return {"message": "Folder removed."}

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.integrations.auth import get_current_user
from src.interfaces.chat_service import IChatService
from src.models.user import User
from src.schemas.chat import ChatDetailOut, ChatOut
from src.schemas.query import QueryAnswer
from src.schemas.system import MessageResponse
from src.services.chat_service import get_chat_service

router = APIRouter(prefix="/chats", tags=["chats"])


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ChatUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    folder_id: str | None = Field(
        default=None,
        description="Optional. Target folder ID. Omit to leave the folder unchanged.",
    )


class MessageCreate(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    chat_id: str | None = None


@router.get("", response_model=list[ChatOut], summary="List chats")
async def list_chats(
    folder_id: str | None = Query(
        default=None,
        description="Optional. Filter chats by folder ID. Omit to list across all folders.",
    ),
    current_user: User | None = Depends(get_current_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    return chat_service.list(_clean_optional(folder_id))


@router.post(
    "/messages",
    response_model=QueryAnswer,
    summary="Send a message (RAG ask); creates a chat if chat_id is omitted",
)
async def send_message(
    payload: MessageCreate,
    current_user: User | None = Depends(get_current_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    user_id = current_user.id if current_user else None
    return chat_service.ask(
        question=payload.question,
        chat_id=payload.chat_id,
        user_id=user_id,
    )


@router.get(
    "/{chat_id}",
    response_model=ChatDetailOut,
    summary="Get chat details with messages",
)
async def get_chat(
    chat_id: str,
    current_user: User | None = Depends(get_current_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    return chat_service.get(chat_id)


@router.patch(
    "/{chat_id}",
    response_model=ChatOut,
    summary="Rename chat and/or move it to a folder",
)
async def update_chat(
    chat_id: str,
    payload: ChatUpdate,
    current_user: User | None = Depends(get_current_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    update_data = payload.model_dump(exclude_unset=True)
    if "folder_id" in update_data:
        update_data["folder_id"] = _clean_optional(update_data["folder_id"])
    if "title" in update_data:
        update_data["title"] = _clean_optional(update_data["title"])
    return chat_service.update(chat_id, update_data)


@router.delete("/{chat_id}", response_model=MessageResponse, summary="Delete a chat")
async def delete_chat(
    chat_id: str,
    current_user: User | None = Depends(get_current_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    chat_service.delete(chat_id)
    return {"message": "Chat removed."}

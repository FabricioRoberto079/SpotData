from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.integrations.auth import get_current_user
from src.interfaces.chat_service import IChatService
from src.models.user import User
from src.schemas.chat import ChatOut
from src.schemas.query import QueryAnswer
from src.schemas.system import MessageResponse
from src.services.chat_service import get_chat_service

router = APIRouter(prefix="/chats", tags=["chats"])


class ChatUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    folder_id: str | None = None


class MessageCreate(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    chat_id: str | None = None
    n_results: int = Field(default=5, ge=1, le=20)


@router.get("", response_model=list[ChatOut], summary="List chats")
async def list_chats(
    folder_id: str | None = None,
    current_user: User | None = Depends(get_current_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    return chat_service.list(folder_id)


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
        n_results=payload.n_results,
    )


@router.get(
    "/messages/{message_id}",
    response_model=QueryAnswer,
    summary="Get a message (question + answer + citations)",
)
async def get_message(
    message_id: str,
    current_user: User | None = Depends(get_current_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    return chat_service.get_message(message_id)


@router.delete(
    "/messages/{message_id}",
    response_model=MessageResponse,
    summary="Delete a message (GDPR/LGPD)",
)
async def delete_message(
    message_id: str,
    current_user: User | None = Depends(get_current_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    chat_service.delete_message(message_id)
    return {"message": "Message removed."}


@router.get("/{chat_id}", response_model=ChatOut, summary="Get chat details")
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
    return chat_service.update(
        chat_id, payload.model_dump(exclude_unset=True)
    )


@router.delete("/{chat_id}", response_model=MessageResponse, summary="Delete a chat")
async def delete_chat(
    chat_id: str,
    current_user: User | None = Depends(get_current_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    chat_service.delete(chat_id)
    return {"message": "Chat removed."}

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.exceptions import DomainError
from src.auth import require_user
from src.interfaces.chat_service import IChatService
from src.models.user import User
from src.schemas.chat import ChatDetailOut, ChatOut, ChatUpdate, MessageCreate
from src.schemas.system import MessageResponse
from src.services.chat_service import get_chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["chats"])


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@router.get("", response_model=list[ChatOut], summary="List chats")
async def list_chats(
    folder_id: str | None = Query(
        default=None,
        description="Optional. Filter chats by folder ID. Omit to list across all folders.",
    ),
    current_user: User = Depends(require_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    return await asyncio.to_thread(
        chat_service.list, _clean_optional(folder_id), current_user.id
    )


def _encode_event(event: dict) -> bytes:
    return (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")


@router.post(
    "/messages",
    summary="Send a message and stream the answer (one JSON object per line)",
)
async def send_message(
    payload: MessageCreate,
    current_user: User = Depends(require_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    event_gen = chat_service.ask_stream(
        question=payload.question,
        chat_id=payload.chat_id,
        user_id=current_user.id,
    )

    # Force first iteration so early errors (validation, not-found, LLM auth, etc.)
    # bubble up BEFORE the StreamingResponse starts — they become proper JSON error
    # responses with the right status code (mirrors `if !Response.HasStarted` in .NET).
    try:
        first_event = await event_gen.__anext__()
    except StopAsyncIteration:
        first_event = None

    async def stream():
        if first_event is not None:
            yield _encode_event(first_event)
        try:
            async for event in event_gen:
                yield _encode_event(event)
        except DomainError as exc:
            logger.warning(
                "stream %s domain-error %s: %s",
                type(exc).__name__,
                exc.status_code,
                exc.message,
            )
            yield _encode_event(
                {
                    "type": "error",
                    "kind": type(exc).__name__.removesuffix("Error").lower() or "domain",
                    "status_code": exc.status_code,
                    "message": exc.message,
                }
            )
        except Exception:
            logger.exception("stream failed mid-iteration")
            yield _encode_event(
                {"type": "error", "kind": "unexpected", "message": "Internal error."}
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{chat_id}",
    response_model=ChatDetailOut,
    summary="Get chat details with messages",
)
async def get_chat(
    chat_id: str,
    current_user: User = Depends(require_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    return await asyncio.to_thread(chat_service.get, chat_id, current_user.id)


@router.patch(
    "/{chat_id}",
    response_model=ChatOut,
    summary="Rename chat and/or move it to a folder",
)
async def update_chat(
    chat_id: str,
    payload: ChatUpdate,
    current_user: User = Depends(require_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    update_data = payload.model_dump(exclude_unset=True)
    if "folder_id" in update_data:
        update_data["folder_id"] = _clean_optional(update_data["folder_id"])
    if "title" in update_data:
        update_data["title"] = _clean_optional(update_data["title"])
    return await asyncio.to_thread(
        chat_service.update, chat_id, update_data, current_user.id
    )


@router.delete("/{chat_id}", response_model=MessageResponse, summary="Delete a chat")
async def delete_chat(
    chat_id: str,
    current_user: User = Depends(require_user),
    chat_service: IChatService = Depends(get_chat_service),
):
    await asyncio.to_thread(chat_service.delete, chat_id, current_user.id)
    return {"message": "Chat removed."}

from typing import Literal

from pydantic import BaseModel, Field

from src.schemas.query import CitationOut


class ChatOut(BaseModel):
    id: str
    title: str
    folder_id: str | None = None
    user_id: str | None = None
    category_id: str | None = None
    created_at: str | None = None


class ChatMessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str | None = None
    status: str | None = None
    citations: list[CitationOut] = Field(default_factory=list)
    time_ms: int | None = None


class ChatDetailOut(ChatOut):
    messages: list[ChatMessageOut] = Field(default_factory=list)


class ChatUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    folder_id: str | None = Field(
        default=None,
        description="Optional. Target folder ID. Omit to leave the folder unchanged.",
    )


class MessageCreate(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    chat_id: str | None = None
    # Chosen only when starting a new chat (chat_id is null); stored on the chat and
    # used to scope retrieval. Omit (or null) to search across every category.
    # Ignored for an existing chat, which keeps the category it was created with.
    category_id: str | None = None

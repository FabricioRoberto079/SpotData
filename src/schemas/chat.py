from typing import Literal

from pydantic import BaseModel, Field

from src.schemas.query import CitationOut


class ChatOut(BaseModel):
    id: str
    title: str
    folder_id: str | None = None
    user_id: str | None = None
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

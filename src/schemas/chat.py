from pydantic import BaseModel


class ChatOut(BaseModel):
    id: str
    title: str
    folder_id: str | None = None
    user_id: str | None = None
    created_at: str | None = None

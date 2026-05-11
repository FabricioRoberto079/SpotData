from __future__ import annotations

from pydantic import BaseModel, Field


class FolderOut(BaseModel):
    id: str
    name: str
    parent_id: str | None = None
    owner_id: str | None = None
    created_at: str | None = None


class FolderNode(FolderOut):
    children: list["FolderNode"] = Field(default_factory=list)


FolderNode.model_rebuild()

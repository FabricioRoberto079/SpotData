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


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: str | None = None


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: str | None = None


FolderNode.model_rebuild()

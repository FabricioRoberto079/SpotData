from pydantic import BaseModel, Field

from src.enums.user_role import UserRole


class CategoryCreate(BaseModel):
    # Stored normalized: special chars stripped, spaces -> '_', UPPERCASE.
    name: str = Field(min_length=1, max_length=120)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class CategoryOut(BaseModel):
    id: str
    name: str
    slug: str
    created_by: str | None = None
    created_at: str | None = None


class AdminUserOut(BaseModel):
    id: str
    name: str
    email: str
    role: str
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserActiveUpdate(BaseModel):
    is_active: bool

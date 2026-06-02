from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.enums.user_role import UserRole
from src.models.base_model import BaseModel


class User(BaseModel):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    role: Mapped[str] = mapped_column(
        String, nullable=False, default=UserRole.VIEWER.value
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    password_hash: Mapped[str] = mapped_column(String, nullable=False)

    documents: Mapped[list["KnowledgeDocument"]] = relationship(back_populates="uploaded_by_user")
    queries: Mapped[list["Query"]] = relationship(back_populates="user")
    assigned_categories: Mapped[list["Category"]] = relationship(
        secondary="user_categories", back_populates="users"
    )

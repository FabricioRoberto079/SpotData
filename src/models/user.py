from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base_model import BaseModel


class User(BaseModel):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="user")
    password_hash: Mapped[str] = mapped_column(String, nullable=False)

    documents: Mapped[list["KnowledgeDocument"]] = relationship(back_populates="uploaded_by_user")
    queries: Mapped[list["Query"]] = relationship(back_populates="user")

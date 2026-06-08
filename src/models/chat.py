from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base_model import BaseModel


class Chat(BaseModel):
    __tablename__ = "chats"

    title: Mapped[str] = mapped_column(String, nullable=False)
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("chat_folders.id"), nullable=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # Chosen when the chat is created; scopes its RAG retrieval to one category.
    # NULL means the chat searches across every category.
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )

    folder: Mapped["ChatFolder | None"] = relationship(back_populates="chats")
    queries: Mapped[list["Query"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan"
    )

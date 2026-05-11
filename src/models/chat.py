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

    folder: Mapped["ChatFolder | None"] = relationship(back_populates="chats")
    queries: Mapped[list["Query"]] = relationship(back_populates="chat")

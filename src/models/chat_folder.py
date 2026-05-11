from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base_model import BaseModel


class ChatFolder(BaseModel):
    __tablename__ = "chat_folders"

    name: Mapped[str] = mapped_column(String, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("chat_folders.id"), nullable=True
    )
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    parent: Mapped["ChatFolder | None"] = relationship(
        back_populates="children", remote_side="ChatFolder.id"
    )
    children: Mapped[list["ChatFolder"]] = relationship(back_populates="parent")
    chats: Mapped[list["Chat"]] = relationship(back_populates="folder")

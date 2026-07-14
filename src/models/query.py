from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import TimestampedBase

if TYPE_CHECKING:
    from src.models.chat import Chat
    from src.models.response import Response
    from src.models.user import User


class Query(TimestampedBase):
    __tablename__ = "queries"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    chat_id: Mapped[str | None] = mapped_column(ForeignKey("chats.id"), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_url: Mapped[str | None] = mapped_column(String, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User | None"] = relationship(back_populates="queries")
    chat: Mapped["Chat | None"] = relationship(back_populates="queries")
    response: Mapped["Response | None"] = relationship(
        back_populates="query", uselist=False, cascade="all, delete-orphan"
    )

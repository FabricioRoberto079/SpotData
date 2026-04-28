from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.Models.base_model import BaseModel


class Query(BaseModel):
    __tablename__ = "queries"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_url: Mapped[str | None] = mapped_column(String, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="queries")
    response: Mapped["Response | None"] = relationship(back_populates="query", uselist=False)

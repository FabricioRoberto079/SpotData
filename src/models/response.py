from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.enums.response_status import ResponseStatus
from src.models.base import TimestampedBase

if TYPE_CHECKING:
    from src.models.evidence_citation import EvidenceCitation
    from src.models.query import Query


class Response(TimestampedBase):
    __tablename__ = "responses"

    query_id: Mapped[str] = mapped_column(ForeignKey("queries.id"), unique=True, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default=ResponseStatus.SUCCESS, nullable=False)
    time_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    query: Mapped["Query"] = relationship(back_populates="response")
    citations: Mapped[list["EvidenceCitation"]] = relationship(
        back_populates="response", cascade="all, delete-orphan"
    )

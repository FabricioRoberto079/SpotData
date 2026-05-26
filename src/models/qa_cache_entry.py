from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.config import embedding_dimension
from src.models.base_model import Base


class QaCacheEntry(Base):
    __tablename__ = "qa_cache_entries"
    __table_args__ = (Index("ix_qa_cache_entries_created_at", "created_at"),)

    question_key: Mapped[str] = mapped_column(String, primary_key=True)
    normalized_question: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    embedding = mapped_column(
        Vector(embedding_dimension()).with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

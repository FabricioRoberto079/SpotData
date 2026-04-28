from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.Enums.vectorization_status import VectorizationStatus
from src.Models.base_model import BaseModel


class KnowledgeDocument(BaseModel):
    __tablename__ = "knowledge_documents"

    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    vectorization_status: Mapped[str] = mapped_column(
        String, default=VectorizationStatus.PENDING, nullable=False
    )
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    uploaded_by_user: Mapped["User"] = relationship(back_populates="documents")
    citations: Mapped[list["EvidenceCitation"]] = relationship(back_populates="document")

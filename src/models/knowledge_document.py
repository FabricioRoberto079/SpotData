from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base_model import BaseModel


class KnowledgeDocument(BaseModel):
    __tablename__ = "knowledge_documents"

    file_name: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_folders.id"), nullable=True
    )
    uploaded_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    folder: Mapped["DocumentFolder | None"] = relationship(back_populates="documents")
    uploaded_by_user: Mapped["User | None"] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        order_by="DocumentVersion.version_number",
        cascade="all, delete-orphan",
    )
    citations: Mapped[list["EvidenceCitation"]] = relationship(back_populates="document")

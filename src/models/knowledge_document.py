from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base_model import BaseModel

if TYPE_CHECKING:
    from src.models.document_version import DocumentVersion
    from src.models.evidence_citation import EvidenceCitation
    from src.models.user import User


class KnowledgeDocument(BaseModel):
    __tablename__ = "knowledge_documents"

    file_name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    uploaded_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    uploaded_by_user: Mapped["User | None"] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        order_by="DocumentVersion.version_number",
        cascade="all, delete-orphan",
    )
    citations: Mapped[list["EvidenceCitation"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

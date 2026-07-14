from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import TimestampedBase

if TYPE_CHECKING:
    from src.models.document_version import DocumentVersion
    from src.models.evidence_citation import EvidenceCitation
    from src.models.user import User


class KnowledgeDocument(TimestampedBase):
    __tablename__ = "knowledge_documents"

    file_name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    uploaded_by_user: Mapped["User | None"] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        order_by="DocumentVersion.version_number",
        cascade="all, delete-orphan",
    )
    citations: Mapped[list["EvidenceCitation"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    @property
    def latest_version(self) -> "DocumentVersion | None":
        if not self.versions:
            return None
        return max(self.versions, key=lambda v: v.version_number)

    def find_version(self, version_number: int | None = None) -> "DocumentVersion | None":
        """Version by number, or the latest one when no number is given."""
        if version_number is None:
            return self.latest_version
        return next((v for v in self.versions if v.version_number == version_number), None)

    def find_version_by_id(self, version_id: str) -> "DocumentVersion | None":
        return next((v for v in self.versions if v.id == version_id), None)

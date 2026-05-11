from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.enums.vectorization_status import VectorizationStatus
from src.models.base_model import BaseModel


class DocumentVersion(BaseModel):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version"),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    file_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    vectorization_status: Mapped[str] = mapped_column(
        String, default=VectorizationStatus.PENDING, nullable=False
    )
    vector_id: Mapped[str | None] = mapped_column(String, nullable=True)

    document: Mapped["KnowledgeDocument"] = relationship(back_populates="versions")

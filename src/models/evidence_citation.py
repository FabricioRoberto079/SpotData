from sqlalchemy import Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base_model import BaseModel


class EvidenceCitation(BaseModel):
    __tablename__ = "evidence_citations"

    response_id: Mapped[str] = mapped_column(ForeignKey("responses.id"), nullable=False)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id"), nullable=False
    )
    document_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True
    )
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)

    response: Mapped["Response"] = relationship(back_populates="citations")
    document: Mapped["KnowledgeDocument"] = relationship(back_populates="citations")

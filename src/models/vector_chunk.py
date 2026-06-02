from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.config import embedding_dimension
from src.models.base_model import BaseModel


class VectorChunk(BaseModel):
    __tablename__ = "vector_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_number",
            "chunk_index",
            name="uq_vector_chunk_doc_version_idx",
        ),
        Index("ix_vector_chunks_document_id", "document_id"),
        Index("ix_vector_chunks_is_latest", "is_latest"),
        Index("ix_vector_chunks_category_latest", "category_id", "is_latest"),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(
        Vector(embedding_dimension()).with_variant(JSON(), "sqlite"),
        nullable=False,
    )

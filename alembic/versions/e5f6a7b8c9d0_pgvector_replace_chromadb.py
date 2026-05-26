"""replace chromadb with pgvector tables

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from src.config import embedding_dimension


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    dim = embedding_dimension()

    op.create_table(
        "vector_chunks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("is_latest", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(dim), nullable=False),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            "chunk_index",
            name="uq_vector_chunk_doc_version_idx",
        ),
    )
    op.create_index(
        "ix_vector_chunks_document_id", "vector_chunks", ["document_id"]
    )
    op.create_index(
        "ix_vector_chunks_is_latest", "vector_chunks", ["is_latest"]
    )
    # NOTE: HNSW index omitted — pgvector's HNSW caps at 2000 dimensions and
    # text-embedding-3-large has 3072. Sequential scan is fine for low volumes;
    # for production, switch to `halfvec(N)` + `halfvec_cosine_ops` (supports
    # up to 4000) or pick a 1536-dim embedding model.

    op.create_table(
        "qa_cache_entries",
        sa.Column("question_key", sa.String(), primary_key=True),
        sa.Column("normalized_question", sa.Text(), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("embedding", Vector(dim), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_qa_cache_entries_created_at", "qa_cache_entries", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_qa_cache_entries_created_at", table_name="qa_cache_entries")
    op.drop_table("qa_cache_entries")

    op.drop_index("ix_vector_chunks_is_latest", table_name="vector_chunks")
    op.drop_index("ix_vector_chunks_document_id", table_name="vector_chunks")
    op.drop_table("vector_chunks")
    # Leave the extension installed — other apps may depend on it.

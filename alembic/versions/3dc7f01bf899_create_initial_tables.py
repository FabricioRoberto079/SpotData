"""create initial tables

Revision ID: 3dc7f01bf899
Revises:
Create Date: 2026-03-31 17:43:51.054031

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "3dc7f01bf899"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_hash", sa.String(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vectorization_status", sa.String(), nullable=False),
        sa.Column("uploaded_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("file_hash"),
    )

    op.create_table(
        "queries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("evidence_url", sa.String(), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
    )

    op.create_table(
        "responses",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("query_id", sa.String(), sa.ForeignKey("queries.id"), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("time_ms", sa.Integer(), nullable=False),
        sa.UniqueConstraint("query_id"),
    )

    op.create_table(
        "evidence_citations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_id", sa.String(), sa.ForeignKey("responses.id"), nullable=False),
        sa.Column("document_id", sa.String(), sa.ForeignKey("knowledge_documents.id"), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("used_excerpt", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
    )

    op.create_table(
        "spots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("file_data", sa.LargeBinary(), nullable=False),
        sa.Column("extracted_text", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("evidence_citations")
    op.drop_table("responses")
    op.drop_table("queries")
    op.drop_table("knowledge_documents")
    op.drop_table("users")
    op.drop_table("spots")

"""add folders and document versioning

Revision ID: a1b2c3d4e5f6
Revises: 3dc7f01bf899
Create Date: 2026-04-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "3dc7f01bf899"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("spots")

    op.create_table(
        "document_folders",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "parent_id",
            sa.String(),
            sa.ForeignKey("document_folders.id"),
            nullable=True,
        ),
        sa.Column(
            "owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=True
        ),
    )

    op.create_table(
        "chat_folders",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "parent_id",
            sa.String(),
            sa.ForeignKey("chat_folders.id"),
            nullable=True,
        ),
        sa.Column(
            "owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=True
        ),
    )

    op.create_table(
        "chats",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column(
            "folder_id",
            sa.String(),
            sa.ForeignKey("chat_folders.id"),
            nullable=True,
        ),
        sa.Column(
            "user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True
        ),
    )

    op.drop_constraint(
        "knowledge_documents_file_hash_key",
        "knowledge_documents",
        type_="unique",
    )
    op.drop_column("knowledge_documents", "file_hash")
    op.drop_column("knowledge_documents", "vectorization_status")
    op.alter_column(
        "knowledge_documents", "uploaded_by", existing_type=sa.String(), nullable=True
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "folder_id",
            sa.String(),
            sa.ForeignKey("document_folders.id"),
            nullable=True,
        ),
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("knowledge_documents.id"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("file_data", sa.LargeBinary(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("vectorization_status", sa.String(), nullable=False),
        sa.Column("vector_id", sa.String(), nullable=True),
        sa.UniqueConstraint(
            "document_id", "version_number", name="uq_document_version"
        ),
    )

    op.add_column(
        "queries",
        sa.Column(
            "chat_id",
            sa.String(),
            sa.ForeignKey("chats.id"),
            nullable=True,
        ),
    )
    op.alter_column(
        "queries", "user_id", existing_type=sa.String(), nullable=True
    )

    op.alter_column(
        "evidence_citations", "page", existing_type=sa.Integer(), nullable=True
    )
    op.add_column(
        "evidence_citations",
        sa.Column(
            "document_version_id",
            sa.String(),
            sa.ForeignKey("document_versions.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("evidence_citations", "document_version_id")
    op.alter_column(
        "evidence_citations", "page", existing_type=sa.Integer(), nullable=False
    )
    op.alter_column(
        "queries", "user_id", existing_type=sa.String(), nullable=False
    )
    op.drop_column("queries", "chat_id")
    op.drop_table("document_versions")
    op.drop_column("knowledge_documents", "folder_id")
    op.alter_column(
        "knowledge_documents", "uploaded_by", existing_type=sa.String(), nullable=False
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("vectorization_status", sa.String(), nullable=False),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("file_hash", sa.String(), nullable=False),
    )
    op.create_unique_constraint(
        "knowledge_documents_file_hash_key",
        "knowledge_documents",
        ["file_hash"],
    )

    op.drop_table("chats")
    op.drop_table("chat_folders")
    op.drop_table("document_folders")

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

"""replace document_folders with category enum on knowledge_documents

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("category", sa.String(), nullable=True),
    )
    op.execute(
        """
        UPDATE knowledge_documents
        SET category = CASE
            WHEN lower(file_name) ~ '\\.(pdf|docx?)$' THEN 'documents'
            WHEN lower(file_name) ~ '\\.(png|jpe?g)$' THEN 'images'
            WHEN lower(file_name) ~ '\\.(txt|md)$' THEN 'text'
            ELSE 'text'
        END
        WHERE category IS NULL
        """
    )
    op.alter_column(
        "knowledge_documents",
        "category",
        existing_type=sa.String(),
        nullable=False,
    )

    op.drop_constraint(
        "knowledge_documents_folder_id_fkey",
        "knowledge_documents",
        type_="foreignkey",
    )
    op.drop_column("knowledge_documents", "folder_id")
    op.drop_table("document_folders")


def downgrade() -> None:
    op.create_table(
        "document_folders",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
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
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "folder_id",
            sa.String(),
            sa.ForeignKey("document_folders.id"),
            nullable=True,
        ),
    )
    op.drop_column("knowledge_documents", "category")

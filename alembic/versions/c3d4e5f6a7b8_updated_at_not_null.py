"""make updated_at NOT NULL and backfill from created_at

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    "users",
    "document_folders",
    "chat_folders",
    "knowledge_documents",
    "document_versions",
    "chats",
    "queries",
    "responses",
    "evidence_citations",
)


def upgrade() -> None:
    for table in TABLES:
        op.execute(
            f"UPDATE {table} SET updated_at = created_at WHERE updated_at IS NULL"
        )
        op.alter_column(
            table,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(
            table,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )

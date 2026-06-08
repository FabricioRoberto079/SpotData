"""add chats.category_id and drop user_categories grants

Revision ID: j0b1c2d3e4f5
Revises: i9a0b1c2d3e4
Create Date: 2026-06-02 21:40:00.000000

Category access is no longer scoped per user: every user may use every category.
- ``chats`` gain ``category_id`` (chosen at creation) so a chat's RAG retrieval is
  limited to a single category; NULL means it searches across every category.
- the ``user_categories`` grant table is dropped.

The category link now lives only on documents (and on chats, for querying).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "j0b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "i9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chats",
        sa.Column(
            "category_id",
            sa.String(),
            sa.ForeignKey("categories.id"),
            nullable=True,
        ),
    )
    op.drop_table("user_categories")


def downgrade() -> None:
    op.create_table(
        "user_categories",
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category_id",
            sa.String(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.drop_column("chats", "category_id")

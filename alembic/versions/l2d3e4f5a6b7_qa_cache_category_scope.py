"""scope qa cache entries by category

Revision ID: l2d3e4f5a6b7
Revises: k1c2d3e4f5a6
Create Date: 2026-06-09

The Q&A cache used to be global, so only category-less chats could read/write
it. Add a ``category_id`` scope column so category-scoped chats can cache too
without leaking answers across categories: lookups match the scope exactly and
the key embeds it. Existing rows were all global answers, so a NULL scope (the
column default) already describes them correctly — no backfill needed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "k1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "qa_cache_entries",
        sa.Column("category_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_qa_cache_entries_category_id", "qa_cache_entries", ["category_id"]
    )
    op.create_foreign_key(
        "fk_qa_cache_entries_category_id",
        "qa_cache_entries",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_qa_cache_entries_category_id", "qa_cache_entries", type_="foreignkey"
    )
    op.drop_index("ix_qa_cache_entries_category_id", table_name="qa_cache_entries")
    op.drop_column("qa_cache_entries", "category_id")

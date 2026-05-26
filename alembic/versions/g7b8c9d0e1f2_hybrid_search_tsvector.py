"""hybrid search: tsvector column on vector_chunks

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-24 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE vector_chunks
        ADD COLUMN tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('portuguese', snippet)) STORED
        """
    )
    op.execute("CREATE INDEX ix_vector_chunks_tsv ON vector_chunks USING GIN (tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vector_chunks_tsv")
    op.execute("ALTER TABLE vector_chunks DROP COLUMN IF EXISTS tsv")

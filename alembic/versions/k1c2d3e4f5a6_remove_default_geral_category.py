"""remove default GERAL category

Revision ID: k1c2d3e4f5a6
Revises: j0b1c2d3e4f5
Create Date: 2026-06-03

The system no longer ships with a default category. A document without a
category is treated as shared ("de todos") and shows up in every search, so
there is no need for a catch-all GERAL bucket. This drops the seeded GERAL
category and unlinks anything that still points to it (documents, chunks and
chats), leaving those rows uncategorized.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "j0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed id used by the original backfill that seeded the GERAL category.
_GERAL_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # Unlink everything that references GERAL so the FK lets us delete it.
    for table in ("knowledge_documents", "vector_chunks", "chats"):
        op.execute(
            sa.text(
                f"UPDATE {table} SET category_id = NULL WHERE category_id = :id"
            ).bindparams(id=_GERAL_ID)
        )
    op.execute(
        sa.text("DELETE FROM categories WHERE id = :id").bindparams(id=_GERAL_ID)
    )


def downgrade() -> None:
    # Best-effort: recreate the GERAL category. Previous links are not restored.
    op.execute(
        sa.text(
            "INSERT INTO categories (id, created_at, updated_at, name, slug) "
            "VALUES (:id, now(), now(), 'GERAL', 'geral') "
            "ON CONFLICT (id) DO NOTHING"
        ).bindparams(id=_GERAL_ID)
    )

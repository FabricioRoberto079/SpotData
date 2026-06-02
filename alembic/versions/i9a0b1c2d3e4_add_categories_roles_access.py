"""add categories, user roles and category-based access

Revision ID: i9a0b1c2d3e4
Revises: h8c9d0e1f2a3
Create Date: 2026-05-26 20:00:00.000000

Introduces category-based access control:
- users gain ``is_active`` and migrate role ``user`` -> ``editor``;
- ``categories`` (admin-managed) and ``user_categories`` (grants);
- ``category_id`` on ``knowledge_documents`` and ``vector_chunks`` for scoping search.

Backfill creates a single "Geral" category, links every existing document,
chunk and user to it so nothing disappears. After deploy, promote one user to
admin manually:  UPDATE users SET role='admin' WHERE email='...';
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "i9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "h8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed id for the backfill "Geral" category (referenced by downgrade too).
_GERAL_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # 1. users.is_active + role migration
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.execute("UPDATE users SET role = 'editor' WHERE role = 'user'")

    # 2. categories
    op.create_table(
        "categories",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column(
            "created_by", sa.String(), sa.ForeignKey("users.id"), nullable=True
        ),
    )

    # 3. user_categories grant table
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

    # 4. category_id on documents and chunks
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "category_id",
            sa.String(),
            sa.ForeignKey("categories.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "vector_chunks",
        sa.Column(
            "category_id",
            sa.String(),
            sa.ForeignKey("categories.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_vector_chunks_category_latest",
        "vector_chunks",
        ["category_id", "is_latest"],
    )

    # 5. backfill — nothing should fall outside a category
    op.execute(
        sa.text(
            "INSERT INTO categories (id, created_at, updated_at, name, slug) "
            "VALUES (:id, now(), now(), 'GERAL', 'geral')"
        ).bindparams(id=_GERAL_ID)
    )
    op.execute(
        sa.text(
            "UPDATE knowledge_documents SET category_id = :id WHERE category_id IS NULL"
        ).bindparams(id=_GERAL_ID)
    )
    op.execute(
        sa.text(
            "UPDATE vector_chunks SET category_id = :id WHERE category_id IS NULL"
        ).bindparams(id=_GERAL_ID)
    )
    op.execute(
        sa.text(
            "INSERT INTO user_categories (user_id, category_id) "
            "SELECT id, :id FROM users"
        ).bindparams(id=_GERAL_ID)
    )


def downgrade() -> None:
    op.drop_index("ix_vector_chunks_category_latest", table_name="vector_chunks")
    op.drop_column("vector_chunks", "category_id")
    op.drop_column("knowledge_documents", "category_id")
    op.drop_table("user_categories")
    op.drop_table("categories")
    op.execute("UPDATE users SET role = 'user' WHERE role = 'editor'")
    op.drop_column("users", "is_active")

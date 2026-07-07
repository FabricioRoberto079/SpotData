"""add upload_sessions table

Revision ID: m3e4f5a6b7c8
Revises: l2d3e4f5a6b7
Create Date: 2026-07-07

Resumable uploads: the client opens a session declaring name and total size,
sends the file in chunks (pausing whenever it wants), asks the server how many
bytes were received to resume from that offset, and completes the session to
run the regular ingestion pipeline. Partial bytes accumulate in ``data`` and
are cleared on completion.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "l2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("category_id", sa.String(), nullable=True),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("total_size", sa.Integer(), nullable=False),
        sa.Column("bytes_received", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_upload_sessions_user_id", "upload_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_upload_sessions_user_id", table_name="upload_sessions")
    op.drop_table("upload_sessions")

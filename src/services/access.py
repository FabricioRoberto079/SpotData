"""Resolve which categories a user may read/operate in.

This is the single source of truth for the access scope used by document listing,
semantic search and chat RAG. Admins are unrestricted (``None`` = all categories);
everyone else is limited to the categories they have been granted.
"""
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.auth import require_user
from src.data.postgres_client import get_session
from src.enums.user_role import UserRole
from src.models.user import User
from src.models.user_category import user_categories


def allowed_category_ids(session: Session, user: User) -> list[str] | None:
    """Category ids the user may access. ``None`` means unrestricted (admin)."""
    if user.role == UserRole.ADMIN.value:
        return None
    rows = (
        session.execute(
            select(user_categories.c.category_id).where(
                user_categories.c.user_id == user.id
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def get_allowed_category_ids(
    current_user: User = Depends(require_user),
    session: Session = Depends(get_session),
) -> list[str] | None:
    """FastAPI dependency wrapping :func:`allowed_category_ids`."""
    return allowed_category_ids(session, current_user)

import re
import unicodedata

from fastapi import Depends
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from src.data.postgres_client import get_session
from src.enums.user_role import UserRole
from src.exceptions import ConflictError, NotFoundError, ValidationError
from src.interfaces.admin_service import IAdminService
from src.models.category import Category
from src.models.user import User
from src.models.user_category import user_categories

# Category every newly-registered user is linked to (see AuthService.register).
DEFAULT_CATEGORY_NAME = "GERAL"
DEFAULT_CATEGORY_SLUG = "geral"


def normalize_category_name(value: str) -> str:
    """Canonical category name: accents stripped, special characters removed, inner
    runs of whitespace collapsed to a single underscore, ends trimmed, UPPERCASE.

    e.g. '  Recursos   Humanos! ' -> 'RECURSOS_HUMANOS'. Returns '' when nothing
    usable remains (caller should reject it)."""
    decomposed = unicodedata.normalize("NFKD", value)
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", "", no_accents)
    collapsed = re.sub(r"\s+", " ", cleaned).strip()
    return collapsed.replace(" ", "_").upper()


class AdminService(IAdminService):
    def __init__(self, session: Session) -> None:
        self._session = session

    # --- serialization ---
    @staticmethod
    def _category_out(c: Category) -> dict:
        return {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "created_by": c.created_by,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }

    @staticmethod
    def _user_out(u: User) -> dict:
        return {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
        }

    # --- lookups ---
    def _get_category(self, category_id: str) -> Category:
        category = self._session.get(Category, category_id)
        if category is None:
            raise NotFoundError(f"Category not found: {category_id}")
        return category

    def _get_user(self, user_id: str) -> User:
        user = self._session.get(User, user_id)
        if user is None:
            raise NotFoundError(f"User not found: {user_id}")
        return user

    def _slug_taken(self, slug: str, exclude_id: str | None = None) -> bool:
        stmt = select(Category.id).where(Category.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(Category.id != exclude_id)
        return self._session.execute(stmt).first() is not None

    # --- categories ---
    def create_category(
        self, name: str, created_by: str | None = None
    ) -> dict:
        normalized = normalize_category_name(name)
        if not normalized:
            raise ValidationError("Category name has no usable characters.")
        final_slug = normalized.lower()
        try:
            if self._slug_taken(final_slug):
                raise ConflictError(f"Category already exists: '{normalized}'.")
            category = Category(
                name=normalized, slug=final_slug, created_by=created_by
            )
            self._session.add(category)
            self._session.commit()
            self._session.refresh(category)
            return self._category_out(category)
        except Exception:
            self._session.rollback()
            raise

    def list_categories(self) -> list[dict]:
        rows = (
            self._session.execute(select(Category).order_by(Category.name))
            .scalars()
            .all()
        )
        return [self._category_out(c) for c in rows]

    def update_category(self, category_id: str, fields: dict) -> dict:
        try:
            category = self._get_category(category_id)
            if fields.get("name") is not None:
                normalized = normalize_category_name(fields["name"])
                if not normalized:
                    raise ValidationError("Category name has no usable characters.")
                new_slug = normalized.lower()
                if self._slug_taken(new_slug, exclude_id=category_id):
                    raise ConflictError(f"Category already exists: '{normalized}'.")
                category.name = normalized
                category.slug = new_slug
            self._session.commit()
            self._session.refresh(category)
            return self._category_out(category)
        except Exception:
            self._session.rollback()
            raise

    def delete_category(self, category_id: str) -> None:
        try:
            category = self._get_category(category_id)
            self._session.delete(category)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    # --- grants ---
    def assign_category(self, user_id: str, category_id: str) -> None:
        try:
            self._get_user(user_id)
            self._get_category(category_id)
            already = self._session.execute(
                select(user_categories.c.user_id).where(
                    user_categories.c.user_id == user_id,
                    user_categories.c.category_id == category_id,
                )
            ).first()
            if already is None:
                self._session.execute(
                    insert(user_categories).values(
                        user_id=user_id, category_id=category_id
                    )
                )
                self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def unassign_category(self, user_id: str, category_id: str) -> None:
        try:
            self._session.execute(
                delete(user_categories).where(
                    user_categories.c.user_id == user_id,
                    user_categories.c.category_id == category_id,
                )
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def categories_for_user(self, user_id: str) -> list[dict]:
        self._get_user(user_id)
        rows = (
            self._session.execute(
                select(Category)
                .join(
                    user_categories,
                    user_categories.c.category_id == Category.id,
                )
                .where(user_categories.c.user_id == user_id)
                .order_by(Category.name)
            )
            .scalars()
            .all()
        )
        return [self._category_out(c) for c in rows]

    # --- user management ---
    def list_users(self) -> list[dict]:
        rows = (
            self._session.execute(select(User).order_by(User.email)).scalars().all()
        )
        return [self._user_out(u) for u in rows]

    def set_user_role(self, user_id: str, role: UserRole) -> dict:
        try:
            user = self._get_user(user_id)
            user.role = role.value
            self._session.commit()
            self._session.refresh(user)
            return self._user_out(user)
        except Exception:
            self._session.rollback()
            raise

    def set_user_active(self, user_id: str, is_active: bool) -> dict:
        try:
            user = self._get_user(user_id)
            user.is_active = is_active
            self._session.commit()
            self._session.refresh(user)
            return self._user_out(user)
        except Exception:
            self._session.rollback()
            raise


def get_admin_service(session: Session = Depends(get_session)) -> IAdminService:
    return AdminService(session)

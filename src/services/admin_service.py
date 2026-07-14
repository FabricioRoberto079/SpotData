import re
import unicodedata

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.data.postgres_client import get_session, transaction
from src.enums.user_role import UserRole
from src.exceptions import ConflictError, NotFoundError, ValidationError
from src.models.category import Category
from src.models.chat import Chat
from src.models.knowledge_document import KnowledgeDocument
from src.models.user import User


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


class AdminService:
    def __init__(self, session: Session) -> None:
        self._session = session

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

    def create_category(self, name: str, created_by: str | None = None) -> dict:
        normalized = normalize_category_name(name)
        if not normalized:
            raise ValidationError("Category name has no usable characters.")
        final_slug = normalized.lower()
        with transaction(self._session):
            if self._slug_taken(final_slug):
                raise ConflictError(f"Category already exists: '{normalized}'.")
            category = Category(name=normalized, slug=final_slug, created_by=created_by)
            self._session.add(category)
        self._session.refresh(category)
        return self._category_out(category)

    def list_categories(self) -> list[dict]:
        rows = self._session.execute(select(Category).order_by(Category.name)).scalars().all()
        return [self._category_out(c) for c in rows]

    def update_category(self, category_id: str, fields: dict) -> dict:
        with transaction(self._session):
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
        self._session.refresh(category)
        return self._category_out(category)

    def _count_where(self, model, *conditions) -> int:
        return self._session.execute(
            select(func.count()).select_from(model).where(*conditions)
        ).scalar_one()

    def delete_category(self, category_id: str) -> None:
        with transaction(self._session):
            category = self._get_category(category_id)
            documents = self._count_where(
                KnowledgeDocument, KnowledgeDocument.category_id == category_id
            )
            if documents:
                raise ConflictError(
                    f"Category '{category.name}' still has {documents} document(s); "
                    "move or delete them first."
                )
            chats = self._count_where(Chat, Chat.category_id == category_id)
            if chats:
                raise ConflictError(
                    f"Category '{category.name}' still has {chats} chat(s) scoped to it."
                )
            self._session.delete(category)

    def list_users(self) -> list[dict]:
        rows = self._session.execute(select(User).order_by(User.email)).scalars().all()
        return [self._user_out(u) for u in rows]

    def _ensure_not_last_admin(self, user: User) -> None:
        if user.role != UserRole.ADMIN.value or not user.is_active:
            return
        active_admins = self._count_where(
            User, User.role == UserRole.ADMIN.value, User.is_active.is_(True)
        )
        if active_admins <= 1:
            raise ConflictError("Cannot demote or deactivate the last active admin.")

    def set_user_role(self, user_id: str, role: UserRole) -> dict:
        with transaction(self._session):
            user = self._get_user(user_id)
            if role != UserRole.ADMIN:
                self._ensure_not_last_admin(user)
            user.role = role.value
        self._session.refresh(user)
        return self._user_out(user)

    def set_user_active(self, user_id: str, is_active: bool) -> dict:
        with transaction(self._session):
            user = self._get_user(user_id)
            if not is_active:
                self._ensure_not_last_admin(user)
            user.is_active = is_active
        self._session.refresh(user)
        return self._user_out(user)


def get_admin_service(session: Session = Depends(get_session)) -> AdminService:
    return AdminService(session)

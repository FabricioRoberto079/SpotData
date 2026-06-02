from abc import ABC, abstractmethod

from src.enums.user_role import UserRole


class IAdminService(ABC):
    # --- categories ---
    @abstractmethod
    def create_category(self, name: str, created_by: str | None = None) -> dict: ...

    @abstractmethod
    def list_categories(self) -> list[dict]: ...

    @abstractmethod
    def update_category(self, category_id: str, fields: dict) -> dict: ...

    @abstractmethod
    def delete_category(self, category_id: str) -> None: ...

    # --- user <-> category grants ---
    @abstractmethod
    def assign_category(self, user_id: str, category_id: str) -> None: ...

    @abstractmethod
    def unassign_category(self, user_id: str, category_id: str) -> None: ...

    @abstractmethod
    def categories_for_user(self, user_id: str) -> list[dict]: ...

    # --- user management ---
    @abstractmethod
    def list_users(self) -> list[dict]: ...

    @abstractmethod
    def set_user_role(self, user_id: str, role: UserRole) -> dict: ...

    @abstractmethod
    def set_user_active(self, user_id: str, is_active: bool) -> dict: ...

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"

    @property
    def can_upload(self) -> bool:
        """Admins and editors may ingest documents; viewers are read-only."""
        return self in (UserRole.ADMIN, UserRole.EDITOR)

    @property
    def is_admin(self) -> bool:
        return self is UserRole.ADMIN

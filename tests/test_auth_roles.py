import pytest

from src.auth import require_admin, require_role
from src.enums.user_role import UserRole
from src.exceptions import ForbiddenError
from src.models.user import User


def _user(role: UserRole) -> User:
    return User(id="u1", name="U", email="u@x.com", role=role.value, password_hash="x")


def test_user_role_can_upload():
    assert UserRole.ADMIN.can_upload is True
    assert UserRole.EDITOR.can_upload is True
    assert UserRole.VIEWER.can_upload is False


def test_require_role_allows_listed_role():
    dep = require_role(UserRole.EDITOR, UserRole.ADMIN)
    user = _user(UserRole.EDITOR)
    assert dep(current_user=user) is user


def test_require_role_rejects_other_role():
    dep = require_role(UserRole.ADMIN)
    with pytest.raises(ForbiddenError):
        dep(current_user=_user(UserRole.VIEWER))


def test_require_admin_rejects_non_admin():
    with pytest.raises(ForbiddenError):
        require_admin(current_user=_user(UserRole.EDITOR))

import pytest

from src.exceptions import ConflictError, UnauthorizedError
from src.services.auth_service import AuthService


def test_register_returns_token_and_user(session):
    svc = AuthService(session)
    out = svc.register("Alice", "alice@example.com", "secret123")
    assert out["token_type"] == "bearer"
    assert out["access_token"]
    assert out["user"]["email"] == "alice@example.com"


def test_duplicate_email_raises_conflict(session):
    svc = AuthService(session)
    svc.register("A", "a@x.com", "secret123")
    with pytest.raises(ConflictError):
        svc.register("Dup", "a@x.com", "other-pass")


def test_login_with_wrong_password_raises_unauthorized(session):
    svc = AuthService(session)
    svc.register("A", "a@x.com", "secret123")
    with pytest.raises(UnauthorizedError):
        svc.login("a@x.com", "wrong")


def test_login_unknown_email_raises_unauthorized(session):
    with pytest.raises(UnauthorizedError):
        AuthService(session).login("nope@x.com", "anything")


def test_login_success(session):
    svc = AuthService(session)
    svc.register("A", "a@x.com", "secret123")
    out = svc.login("a@x.com", "secret123")
    assert out["access_token"]
    assert out["user"]["email"] == "a@x.com"

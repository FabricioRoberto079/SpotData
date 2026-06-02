import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.auth import verify_password
from src.exceptions import UnauthorizedError
from src.interfaces.email_sender import IEmailSender
from src.models.password_reset_code import PasswordResetCode
from src.models.user import User
from src.services.auth_service import AuthService


class FakeEmailSender(IEmailSender):
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})


def _extract_code(body: str) -> str:
    match = re.search(r"\b(\d{6})\b", body)
    assert match, f"no 6-digit code in email body: {body!r}"
    return match.group(1)


def _register(session, sender, email="user@x.com", password="oldpass123"):
    service = AuthService(session, sender)
    service.register(name="User", email=email, password=password)
    return service


def _user(session, email="user@x.com") -> User:
    return session.scalars(select(User).where(User.email == email)).one()


def test_login_unknown_email_raises_unauthorized(session):
    with pytest.raises(UnauthorizedError):
        AuthService(session, FakeEmailSender()).login("nope@x.com", "anything")


def test_forgot_password_unknown_email_is_silent(session):
    sender = FakeEmailSender()
    AuthService(session, sender).request_password_reset("ghost@x.com")

    assert sender.sent == []
    assert session.scalars(select(PasswordResetCode)).all() == []


def test_forgot_password_emails_a_code_for_a_known_user(session):
    sender = FakeEmailSender()
    service = _register(session, sender)

    service.request_password_reset("user@x.com")

    assert len(sender.sent) == 1
    assert sender.sent[0]["to"] == "user@x.com"
    code = _extract_code(sender.sent[0]["body"])

    stored = session.scalars(select(PasswordResetCode)).one()
    # The code is stored hashed, never in clear text.
    assert stored.code_hash != code
    assert verify_password(code, stored.code_hash)


def test_requesting_a_new_code_invalidates_the_previous_one(session):
    sender = FakeEmailSender()
    service = _register(session, sender)

    service.request_password_reset("user@x.com")
    service.request_password_reset("user@x.com")

    # Only the newest unused code survives.
    codes = session.scalars(select(PasswordResetCode)).all()
    assert len(codes) == 1


def test_reset_password_with_valid_code_changes_the_password(session):
    sender = FakeEmailSender()
    service = _register(session, sender)
    service.request_password_reset("user@x.com")
    code = _extract_code(sender.sent[0]["body"])

    service.reset_password("user@x.com", code, "newpass456")

    user = _user(session)
    assert verify_password("newpass456", user.password_hash)
    assert not verify_password("oldpass123", user.password_hash)


def test_reset_password_marks_the_code_used_so_it_cannot_be_replayed(session):
    sender = FakeEmailSender()
    service = _register(session, sender)
    service.request_password_reset("user@x.com")
    code = _extract_code(sender.sent[0]["body"])

    service.reset_password("user@x.com", code, "newpass456")

    with pytest.raises(UnauthorizedError):
        service.reset_password("user@x.com", code, "another789")


def test_reset_password_wrong_code_raises_and_counts_an_attempt(session):
    sender = FakeEmailSender()
    service = _register(session, sender)
    service.request_password_reset("user@x.com")
    real = _extract_code(sender.sent[0]["body"])
    wrong = "000000" if real != "000000" else "111111"

    with pytest.raises(UnauthorizedError):
        service.reset_password("user@x.com", wrong, "newpass456")

    stored = session.scalars(select(PasswordResetCode)).one()
    assert stored.attempts == 1
    # Original password is untouched.
    assert verify_password("oldpass123", _user(session).password_hash)


def test_reset_password_expired_code_raises(session):
    sender = FakeEmailSender()
    service = _register(session, sender)
    service.request_password_reset("user@x.com")
    code = _extract_code(sender.sent[0]["body"])

    stored = session.scalars(select(PasswordResetCode)).one()
    stored.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.commit()

    with pytest.raises(UnauthorizedError):
        service.reset_password("user@x.com", code, "newpass456")


def test_reset_password_unknown_email_raises(session):
    with pytest.raises(UnauthorizedError):
        AuthService(session, FakeEmailSender()).reset_password(
            "ghost@x.com", "123456", "newpass456"
        )


def test_register_links_user_to_default_category(session):
    from src.models.category import Category
    from src.services.access import allowed_category_ids
    from src.services.admin_service import DEFAULT_CATEGORY_SLUG

    _register(session, FakeEmailSender(), email="new@x.com")
    user = _user(session, "new@x.com")

    geral = session.scalars(
        select(Category).where(Category.slug == DEFAULT_CATEGORY_SLUG)
    ).one()
    assert allowed_category_ids(session, user) == [geral.id]


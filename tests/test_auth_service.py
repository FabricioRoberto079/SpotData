import pytest

from src.exceptions import UnauthorizedError
from src.services.auth_service import AuthService


def test_login_unknown_email_raises_unauthorized(session):
    with pytest.raises(UnauthorizedError):
        AuthService(session).login("nope@x.com", "anything")

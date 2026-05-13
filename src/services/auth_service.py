from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.data.postgres_client import get_session
from src.exceptions import ConflictError, UnauthorizedError
from src.integrations.auth import hash_password, issue_token, verify_password
from src.interfaces.auth_service import IAuthService
from src.models.user import User


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
    }


class AuthService(IAuthService):
    def __init__(self, session: Session) -> None:
        self._session = session

    def register(
        self, name: str, email: str, password: str, role: str = "user"
    ) -> dict:
        email_norm = email.strip().lower()
        try:
            existing = self._session.execute(
                select(User).where(User.email == email_norm)
            ).scalar_one_or_none()
            if existing is not None:
                raise ConflictError("Email already registered.")

            user = User(
                name=name.strip(),
                email=email_norm,
                role=role.strip() or "user",
                password_hash=hash_password(password),
            )
            self._session.add(user)
            self._session.commit()
            self._session.refresh(user)
        except Exception:
            self._session.rollback()
            raise

        return _user_out(user)

    def login(self, email: str, password: str) -> dict:
        email_norm = email.strip().lower()
        user = self._session.execute(
            select(User).where(User.email == email_norm)
        ).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid email or password.")

        token, _ = issue_token(user)
        return {"access_token": token}


def get_auth_service(session: Session = Depends(get_session)) -> IAuthService:
    return AuthService(session)

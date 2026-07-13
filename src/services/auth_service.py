from contextlib import suppress
from datetime import UTC, datetime, timedelta

from fastapi import Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.auth import (
    generate_reset_code,
    hash_password,
    issue_token,
    verify_password,
)
from src.data.postgres_client import get_session, transaction
from src.enums.user_role import UserRole
from src.exceptions import ConflictError, UnauthorizedError
from src.integrations.email import get_email_sender
from src.interfaces.auth_service import IAuthService
from src.interfaces.email_sender import IEmailSender
from src.models.password_reset_code import PasswordResetCode
from src.models.user import User

_CODE_TTL_MINUTES = 15
_MAX_ATTEMPTS = 5
_RESET_EMAIL_SUBJECT = "SpotData — código de redefinição de senha"


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
    }


def _reset_email_body(name: str, code: str) -> str:
    return (
        f"Olá {name},\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta SpotData.\n\n"
        f"Seu código de redefinição é: {code}\n\n"
        f"Ele expira em {_CODE_TTL_MINUTES} minutos. "
        "Se você não fez essa solicitação, ignore este email.\n"
    )


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; normalize to aware UTC for comparison."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class AuthService(IAuthService):
    def __init__(self, session: Session, email_sender: IEmailSender | None = None) -> None:
        self._session = session
        self._email_sender = email_sender or get_email_sender()

    def register(self, name: str, email: str, password: str) -> dict:
        email_norm = email.strip().lower()
        with transaction(self._session):
            existing = self._session.execute(
                select(User).where(User.email == email_norm)
            ).scalar_one_or_none()
            if existing is not None:
                raise ConflictError("Email already registered.")

            user = User(
                name=name.strip(),
                email=email_norm,
                role=UserRole.VIEWER.value,
                password_hash=hash_password(password),
            )
            self._session.add(user)
        self._session.refresh(user)

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

    def request_password_reset(self, email: str) -> None:
        email_norm = email.strip().lower()
        user = self._session.execute(
            select(User).where(User.email == email_norm)
        ).scalar_one_or_none()
        if user is None:
            return

        code = generate_reset_code()
        expires_at = datetime.now(UTC) + timedelta(minutes=_CODE_TTL_MINUTES)
        with transaction(self._session):
            self._session.execute(
                delete(PasswordResetCode).where(
                    PasswordResetCode.user_id == user.id,
                    PasswordResetCode.used_at.is_(None),
                )
            )
            self._session.add(
                PasswordResetCode(
                    user_id=user.id,
                    code_hash=hash_password(code),
                    expires_at=expires_at,
                )
            )

        self._email_sender.send(
            to=user.email,
            subject=_RESET_EMAIL_SUBJECT,
            body=_reset_email_body(user.name, code),
        )

    def reset_password(self, email: str, code: str, new_password: str) -> None:
        email_norm = email.strip().lower()
        user = self._session.execute(
            select(User).where(User.email == email_norm)
        ).scalar_one_or_none()

        record = None
        if user is not None:
            record = (
                self._session.execute(
                    select(PasswordResetCode)
                    .where(
                        PasswordResetCode.user_id == user.id,
                        PasswordResetCode.used_at.is_(None),
                    )
                    .order_by(PasswordResetCode.created_at.desc())
                )
                .scalars()
                .first()
            )

        invalid = UnauthorizedError("Invalid or expired reset code.")
        if user is None or record is None:
            raise invalid

        now = datetime.now(UTC)
        if _as_utc(record.expires_at) < now or record.attempts >= _MAX_ATTEMPTS:
            raise invalid

        if not verify_password(code, record.code_hash):
            with suppress(Exception), transaction(self._session):
                record.attempts += 1
            raise invalid

        with transaction(self._session):
            user.password_hash = hash_password(new_password)
            record.used_at = now


def get_auth_service(session: Session = Depends(get_session)) -> IAuthService:
    return AuthService(session, get_email_sender())

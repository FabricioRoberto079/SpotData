from datetime import datetime, timedelta, timezone

from fastapi import Depends
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from src.auth import (
    generate_reset_code,
    hash_password,
    issue_token,
    verify_password,
)
from src.data.postgres_client import get_session
from src.enums.user_role import UserRole
from src.exceptions import ConflictError, UnauthorizedError
from src.integrations.email import get_email_sender
from src.interfaces.auth_service import IAuthService
from src.interfaces.email_sender import IEmailSender
from src.models.category import Category
from src.models.password_reset_code import PasswordResetCode
from src.models.user import User
from src.models.user_category import user_categories
from src.services.admin_service import DEFAULT_CATEGORY_NAME, DEFAULT_CATEGORY_SLUG

# Reset codes are short-lived and brute-force limited. These are deliberate
# constants, not env config — tune here if the policy changes.
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
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class AuthService(IAuthService):
    def __init__(
        self, session: Session, email_sender: IEmailSender | None = None
    ) -> None:
        self._session = session
        self._email_sender = email_sender or get_email_sender()

    def _ensure_default_category(self) -> Category:
        """Get (or lazily create) the default category every new user is linked to."""
        category = self._session.execute(
            select(Category).where(Category.slug == DEFAULT_CATEGORY_SLUG)
        ).scalar_one_or_none()
        if category is None:
            category = Category(
                name=DEFAULT_CATEGORY_NAME, slug=DEFAULT_CATEGORY_SLUG
            )
            self._session.add(category)
            self._session.flush()
        return category

    def register(self, name: str, email: str, password: str) -> dict:
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
                role=UserRole.VIEWER.value,
                password_hash=hash_password(password),
            )
            self._session.add(user)
            self._session.flush()

            # New users start linked to the default category so they can search
            # something immediately; the admin grants further access later.
            default_category = self._ensure_default_category()
            self._session.execute(
                insert(user_categories).values(
                    user_id=user.id, category_id=default_category.id
                )
            )

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

    def request_password_reset(self, email: str) -> None:
        email_norm = email.strip().lower()
        user = self._session.execute(
            select(User).where(User.email == email_norm)
        ).scalar_one_or_none()
        # Never reveal whether the email is registered: silently no-op otherwise.
        if user is None:
            return

        code = generate_reset_code()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=_CODE_TTL_MINUTES)
        try:
            # Drop any previous unused codes so only the newest one is valid.
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
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        # Send only after the code is persisted, so a send failure never leaves
        # the user with a code we can't verify.
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

        # Generic error for every failure mode — no oracle for attackers.
        invalid = UnauthorizedError("Invalid or expired reset code.")
        if user is None or record is None:
            raise invalid

        now = datetime.now(timezone.utc)
        if _as_utc(record.expires_at) < now or record.attempts >= _MAX_ATTEMPTS:
            raise invalid

        if not verify_password(code, record.code_hash):
            try:
                record.attempts += 1
                self._session.commit()
            except Exception:
                self._session.rollback()
            raise invalid

        try:
            user.password_hash = hash_password(new_password)
            record.used_at = now
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise


def get_auth_service(session: Session = Depends(get_session)) -> IAuthService:
    return AuthService(session, get_email_sender())

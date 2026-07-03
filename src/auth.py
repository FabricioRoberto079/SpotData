from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.config import required_env, required_int
from src.data.postgres_client import SessionLocal
from src.enums.user_role import UserRole
from src.exceptions import ForbiddenError, UnauthorizedError
from src.models.user import User

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


class AuthError(UnauthorizedError):
    """Raised on any auth/JWT failure. Handled by the global DomainError handler."""


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed or hashed == "!disabled!":
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def generate_reset_code() -> str:
    """Cryptographically random 6-digit code for password resets."""
    return f"{secrets.randbelow(1_000_000):06d}"


def issue_token(user: User) -> tuple[str, int]:
    secret = required_env("JWT_SECRET")
    minutes = required_int("JWT_EXPIRATION_MINUTES")
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=minutes)
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm=required_env("JWT_ALGORITHM"))
    return token, minutes * 60


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises AuthError on any failure. Shared by the
    HTTP and MCP auth paths so claim/algorithm handling never diverges."""
    secret = required_env("JWT_SECRET")
    algorithm = required_env("JWT_ALGORITHM")
    try:
        return jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc


def authenticate_token(token: str) -> User:
    """Validate a JWT string and return the live User, re-checking existence and
    `is_active` against the database on every call. Raises AuthError otherwise.
    Used by both the HTTP dependency and the MCP transport."""
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("Token has no subject.")

    session: Session = SessionLocal()
    try:
        user = session.get(User, user_id)
        if user is None:
            raise AuthError("Token user no longer exists.")
        if not user.is_active:
            raise AuthError("Account is disabled.")
        session.expunge(user)
        return user
    finally:
        session.close()


def authenticate_request(request: Request) -> User:
    """Validate the Bearer JWT and return the authenticated User. Raises AuthError otherwise."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise AuthError("Authorization header missing or malformed.")
    token = auth_header[7:].strip()
    if not token:
        raise AuthError("Empty token.")
    return authenticate_token(token)


def require_user(current_user: User = Depends(authenticate_request)) -> User:
    return current_user


def require_role(*roles: UserRole):
    """Dependency factory: allow only the listed roles. Reuses authenticate_request,
    so it inherits the same JWT validation and disabled-account check."""
    allowed = {r.value for r in roles}

    def _dependency(current_user: User = Depends(authenticate_request)) -> User:
        if current_user.role not in allowed:
            raise ForbiddenError("Insufficient permissions for this operation.")
        return current_user

    return _dependency


require_admin = require_role(UserRole.ADMIN)

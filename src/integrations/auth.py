from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.data.postgres_client import SessionLocal
from src.models.user import User

logger = logging.getLogger(__name__)

class AuthError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _algorithm() -> str:
    return _required_env("JWT_ALGORITHM")


def _expiration_minutes() -> int:
    raw = _required_env("JWT_EXPIRATION_MINUTES")
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"JWT_EXPIRATION_MINUTES must be an integer, got: {raw!r}"
        ) from exc


def _secret_required() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="JWT_SECRET not configured — auth endpoint unavailable.",
        )
    return secret


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed or hashed == "!disabled!":
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def issue_token(user: User) -> tuple[str, int]:
    secret = _secret_required()
    minutes = _expiration_minutes()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=minutes)
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm=_algorithm())
    return token, minutes * 60


def _decode_token(token: str) -> dict:
    secret = _secret_required()
    try:
        return jwt.decode(token, secret, algorithms=[_algorithm()])
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expired.")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid token: {e}")


def _get_db() -> Session:
    return SessionLocal()


def get_current_user(request: Request) -> User | None:
    if not os.getenv("JWT_SECRET"):
        return None

    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise AuthError("Authorization header missing or malformed.")
    token = auth_header[7:].strip()
    if not token:
        raise AuthError("Empty token.")

    payload = _decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("Token has no subject.")

    session = _get_db()
    try:
        user = session.get(User, user_id)
        if user is None:
            raise AuthError("Token user no longer exists.")
        session.expunge(user)
        return user
    finally:
        session.close()


def require_user(current_user: User | None = Depends(get_current_user)) -> User:
    if current_user is None:
        raise AuthError("This operation requires authentication.")
    return current_user

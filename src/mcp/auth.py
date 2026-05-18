import os

import jwt


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def resolve_user_id() -> str:
    token = _required_env("SPOTDATA_JWT")
    secret = _required_env("JWT_SECRET")
    algorithm = _required_env("JWT_ALGORITHM")
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise RuntimeError("SPOTDATA_JWT expired; reissue it via /auth/login.") from exc
    except jwt.InvalidTokenError as exc:
        raise RuntimeError(f"SPOTDATA_JWT invalid: {exc}") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise RuntimeError("SPOTDATA_JWT has no subject claim.")
    return user_id

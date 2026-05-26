import jwt

from src.config import required_env


def resolve_user_id_from_token(token: str) -> str:
    """Validate a Bearer JWT and return the `sub` claim. Raises RuntimeError on failure."""
    secret = required_env("JWT_SECRET")
    algorithm = required_env("JWT_ALGORITHM")
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise RuntimeError("JWT expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise RuntimeError(f"JWT invalid: {exc}") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise RuntimeError("JWT has no subject claim.")
    return user_id

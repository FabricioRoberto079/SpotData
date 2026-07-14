from src.auth import authenticate_token
from src.models.user import User


def resolve_user_from_token(token: str) -> User:
    """Validate the JWT and confirm the user still exists and is active.

    Mirrors the HTTP auth path (`src.auth.authenticate_token`) so a disabled or
    deleted user's still-valid token stops working on the MCP surface too,
    instead of only being blocked on the REST endpoints.
    """
    return authenticate_token(token)

"""Central env-var access. Always fail loud — never silently default."""
import os


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def required_int(name: str) -> int:
    raw = required_env(name)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got: {raw!r}") from exc


def embedding_dimension() -> int:
    return required_int("EMBEDDING_DIMENSION")

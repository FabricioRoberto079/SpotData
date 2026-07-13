from collections.abc import Generator, Iterator
from contextlib import contextmanager
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import required_env

load_dotenv()


def get_database_url() -> str:
    user = quote_plus(required_env("POSTGRES_USER"))
    password = quote_plus(required_env("POSTGRES_PASSWORD"))
    host = required_env("POSTGRES_HOST")
    port = required_env("POSTGRES_PORT")
    db = required_env("POSTGRES_DB")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


engine = create_engine(get_database_url())
SessionLocal = sessionmaker(bind=engine)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def transaction(session: Session) -> Iterator[Session]:
    """Unit of work: commit on success, rollback and re-raise on any error.

    Intermediate commits inside the block are fine — the final commit is then
    a no-op. `session.refresh()` calls belong after the block."""
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise

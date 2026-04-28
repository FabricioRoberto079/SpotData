from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os


def get_database_url() -> str:
    user = os.getenv("POSTGRES_USER", "spotdata")
    password = os.getenv("POSTGRES_PASSWORD", "spotdata123")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "spotdata")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


engine = create_engine(get_database_url())
SessionLocal = sessionmaker(bind=engine)

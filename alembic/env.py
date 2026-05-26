from logging.config import fileConfig

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, pool

from alembic import context

from src.data.postgres_client import get_database_url
from src.models.base_model import Base

from src.models.user import User  # noqa: F401
from src.models.chat_folder import ChatFolder  # noqa: F401
from src.models.knowledge_document import KnowledgeDocument  # noqa: F401
from src.models.document_version import DocumentVersion  # noqa: F401
from src.models.chat import Chat  # noqa: F401
from src.models.query import Query  # noqa: F401
from src.models.response import Response  # noqa: F401
from src.models.evidence_citation import EvidenceCitation  # noqa: F401
from src.models.vector_chunk import VectorChunk  # noqa: F401
from src.models.qa_cache_entry import QaCacheEntry  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

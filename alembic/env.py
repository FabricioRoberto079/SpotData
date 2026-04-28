from logging.config import fileConfig

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import pool, create_engine

from alembic import context

from src.Data.postgres_client import get_database_url
from src.Models.base_model import Base

# Importa todos os models para que o autogenerate os detecte
from src.Models.User import User  # noqa: F401
from src.Models.KnowledgeDocument import KnowledgeDocument  # noqa: F401
from src.Models.Query import Query  # noqa: F401
from src.Models.Response import Response  # noqa: F401
from src.Models.EvidenceCitation import EvidenceCitation  # noqa: F401
from src.Models.spot import Spot  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
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
    """Run migrations in 'online' mode."""
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

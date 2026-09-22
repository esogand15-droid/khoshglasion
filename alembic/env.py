from logging.config import fileConfig
from sqlalchemy import pool, create_engine
from alembic import context
import os
import sys

# add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.db.base import Base
from backend.app.models import *  # noqa
from backend.app.core.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def get_url():
    # Use DATABASE_URL from env (Railway) and normalize to sync driver for alembic
    url = os.getenv("DATABASE_URL") or get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    # Ensure sync driver for alembic (psycopg2)
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    elif url.startswith("postgresql://"):
        pass
    elif url.startswith("sqlite"):
        pass
    return url

def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool, future=True)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

from logging.config import fileConfig
from sqlalchemy import pool, create_engine
from alembic import context
import os
import sys
import pathlib

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
    # Fallback to SQLite default - never raise, always have a DB
    raw = os.getenv("DATABASE_URL")
    if raw and raw.strip():
        url = raw.strip()
    else:
        try:
            url = get_settings().database_url
        except Exception:
            url = "sqlite:///./data/khoshgelasion.db"
    if not url or not url.strip():
        url = "sqlite:///./data/khoshgelasion.db"
    url = url.strip()
    # Normalize async drivers to sync for alembic
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    elif url.startswith("sqlite+aiosqlite://"):
        url = url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    # Ensure directory exists for sqlite file
    if url.startswith("sqlite"):
        # extract file path: sqlite:///./data/khoshgelasion.db or sqlite:////absolute/path
        try:
            # Remove sqlite:/// prefix
            path_part = url.split("sqlite:///")[-1].split("?")[0].split("#")[0]
            if path_part and path_part != ":memory:" and path_part != "":
                p = pathlib.Path(path_part)
                # relative to /app if needed
                p.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
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

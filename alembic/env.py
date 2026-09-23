from logging.config import fileConfig
import os
import pathlib
import sys

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.db.url import normalize_sync_url
from backend.app.models import *  # noqa: F401,F403

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    raw = os.getenv("DATABASE_URL") or ""
    if not raw.strip():
        try:
            raw = get_settings().database_url
        except Exception:
            raw = "sqlite:///./data/khoshgelasion.db"
    url = normalize_sync_url(raw)
    if url.startswith("sqlite"):
        path_part = url.split("sqlite:///", 1)[-1].split("?", 1)[0]
        if path_part and path_part != ":memory:":
            pathlib.Path(path_part).parent.mkdir(parents=True, exist_ok=True)
    return url


def run_migrations_offline() -> None:
    context.configure(url=get_url(), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
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

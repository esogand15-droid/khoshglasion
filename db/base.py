from collections.abc import AsyncGenerator
import pathlib

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, StaticPool

from backend.app.core.config import get_settings
from backend.app.db.url import normalize_async_url


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None
_engine_url = ""


def _ensure_sqlite_dir(url: str) -> None:
    if "sqlite" not in url:
        return
    path_part = url.split("///", 1)[-1].split("?", 1)[0].split("#", 1)[0]
    if not path_part or path_part == ":memory:":
        return
    parent = pathlib.Path(path_part).parent
    if str(parent) and str(parent) != ".":
        parent.mkdir(parents=True, exist_ok=True)


def get_engine():
    global _engine, _engine_url
    settings = get_settings()
    url, connect_args = normalize_async_url(settings.database_url)
    if _engine is not None and _engine_url == url:
        return _engine

    if _engine is not None:
        # Settings object is cached, so this only happens in tests that reset the cache.
        _engine.sync_engine.dispose()
        _engine = None

    _engine_url = url
    kwargs = {
        "echo": False,
        "future": True,
        "pool_pre_ping": True,
    }
    if url.startswith("sqlite"):
        _ensure_sqlite_dir(url)
        connect_args = {**connect_args, "check_same_thread": False, "timeout": 30}
        kwargs["poolclass"] = StaticPool if ":memory:" in url else NullPool
        kwargs["connect_args"] = connect_args
    else:
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 5
        kwargs["pool_recycle"] = 280
        kwargs["connect_args"] = connect_args

    _engine = create_async_engine(url, **kwargs)

    if url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(_engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()
    return _engine


def get_session_factory():
    global _session_factory, _engine
    engine = get_engine()
    if _session_factory is None or getattr(_session_factory, "bind", None) is not engine:
        _session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

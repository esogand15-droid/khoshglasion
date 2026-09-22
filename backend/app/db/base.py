from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from backend.app.core.config import get_settings

class Base(DeclarativeBase):
    pass

_engine = None
_session_factory = None

def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        
        connect_args = {}
        if url.startswith("sqlite"):
            # Ensure data directory exists
            import os
            db_path = url.replace("sqlite+aiosqlite:///", "")
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
            # SQLite pragmas for better concurrency
            connect_args = {
                "check_same_thread": False,
                "timeout": 30,
            }
        
        _engine = create_async_engine(
            url,
            echo=False,
            future=True,
            connect_args=connect_args,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        
        # Apply SQLite pragmas after engine creation
        if url.startswith("sqlite"):
            from sqlalchemy import event
            from sqlalchemy.pool import Pool
            
            @event.listens_for(_engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA busy_timeout=30000;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
                cursor.execute("PRAGMA cache_size=-32768;")  # 32MB cache
                cursor.close()
    return _engine

def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
    return _session_factory

async def get_db():
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

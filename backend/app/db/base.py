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
        _engine = create_async_engine(url, echo=False, future=True, connect_args=connect_args)
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

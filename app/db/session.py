from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as sa_create_async_engine


def create_async_engine(database_url: str) -> AsyncEngine:
    return sa_create_async_engine(database_url, echo=False, pool_pre_ping=True)


def create_session_factory(
    database_url_or_engine: str | AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    engine = (
        database_url_or_engine
        if isinstance(database_url_or_engine, AsyncEngine)
        else create_async_engine(database_url_or_engine)
    )
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

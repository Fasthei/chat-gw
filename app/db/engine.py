from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.settings import settings


def _make_engine():
    url = settings.database_url
    kwargs: dict = {"echo": False, "pool_pre_ping": True}
    # SQLite (used by tests) does not accept QueuePool kwargs.
    if not url.startswith("sqlite"):
        kwargs["pool_size"] = settings.database_pool_size
        kwargs["max_overflow"] = settings.database_max_overflow
    return create_async_engine(url, **kwargs)


engine = _make_engine()
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session


async def dispose_engine() -> None:
    await engine.dispose()

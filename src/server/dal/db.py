from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from settings import settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return _engine


async def ping() -> None:
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def dispose() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from settings import settings

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return _engine


async def init_schema() -> None:
    sql = _SCHEMA_PATH.read_text()
    engine = get_engine()
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        # asyncpg's prepared-statement protocol rejects multi-statement
        # strings; drop down to the simple-query protocol via execute().
        await raw.driver_connection.execute(sql)
    logger.info("schema initialized", extra={"schema_path": str(_SCHEMA_PATH)})


async def dispose() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None

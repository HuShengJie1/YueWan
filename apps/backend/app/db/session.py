from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings

settings = get_settings()


def _database_engine_options(settings: Settings) -> dict[str, Any]:
    return {
        "echo": settings.debug,
        "hide_parameters": True,
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout_seconds,
        "pool_recycle": settings.db_pool_recycle_seconds,
        "isolation_level": "READ COMMITTED",
        "connect_args": {"connect_timeout": settings.db_connect_timeout_seconds},
    }


def _set_mysql_session_timezone(dbapi_connection: Any, _connection_record: Any) -> None:
    """Keep database-generated and application-written timestamps on UTC."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SET SESSION time_zone = '+00:00'")
    finally:
        cursor.close()


engine = create_async_engine(
    settings.database_url,
    **_database_engine_options(settings),
)
event.listen(engine.sync_engine, "connect", _set_mysql_session_timezone, insert=True)
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Provide one async database session per request or unit of work."""
    async with async_session_factory() as session:
        yield session

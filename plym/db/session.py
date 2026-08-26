from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from plym.settings import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _statement_name() -> str:
    return f"__plym_{uuid4().hex}__"


def engine_options() -> dict[str, Any]:
    if settings.db_pgbouncer:
        return {
            "poolclass": NullPool,
            "connect_args": {
                "prepared_statement_cache_size": 0,
                "prepared_statement_name_func": _statement_name,
            },
        }
    return {
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
    }


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url, **engine_options())
        SQLAlchemyInstrumentor().instrument(engine=_engine.sync_engine)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None

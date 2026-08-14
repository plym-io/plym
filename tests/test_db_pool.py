import pytest
from sqlalchemy.pool import NullPool

from tests.conftest import TEST_MODE

pytestmark = pytest.mark.skipif(
    TEST_MODE != "inprocess", reason="engine options are read from this process's settings"
)


@pytest.mark.asyncio
async def test_pool_options_come_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from plym.db.session import engine_options
    from plym.settings import settings

    monkeypatch.setattr(settings, "db_pgbouncer", False)
    monkeypatch.setattr(settings, "db_pool_size", 2)
    monkeypatch.setattr(settings, "db_max_overflow", 0)
    monkeypatch.setattr(settings, "db_pool_timeout", 7)
    monkeypatch.setattr(settings, "db_pool_recycle", 300)

    options = engine_options()
    assert options["pool_size"] == 2
    assert options["max_overflow"] == 0
    assert options["pool_timeout"] == 7
    assert options["pool_recycle"] == 300
    assert options["pool_pre_ping"] is True
    assert "poolclass" not in options


@pytest.mark.asyncio
async def test_pgbouncer_mode_drops_the_pool_and_the_statement_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plym.db.session import engine_options
    from plym.settings import settings

    monkeypatch.setattr(settings, "db_pgbouncer", True)

    options = engine_options()
    assert options["poolclass"] is NullPool
    assert options["connect_args"]["prepared_statement_cache_size"] == 0

    name_func = options["connect_args"]["prepared_statement_name_func"]
    first, second = name_func(), name_func()
    assert first != second
    assert first.startswith("__plym_")


@pytest.mark.asyncio
async def test_pgbouncer_mode_builds_a_working_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from plym.db.session import engine_options
    from plym.settings import settings

    monkeypatch.setattr(settings, "db_pgbouncer", True)
    engine = create_async_engine(settings.database_url, **engine_options())
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT count(*) FROM public.pl_posts"))
            assert result.scalar_one() >= 0
    finally:
        await engine.dispose()

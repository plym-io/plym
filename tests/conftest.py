import asyncio
import io
import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from PIL import Image

TEST_MODES = ("live", "inprocess")

_DESTRUCTIVE = (
    "This suite creates, mutates and deletes posts, users and media in whatever it is "
    "pointed at, so the target must be named explicitly and never defaulted."
)


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


TEST_MODE = _env("PLYM_TEST_MODE") or ("live" if _env("PLYM_TEST_BASE_URL") else "")
if not TEST_MODE:
    raise RuntimeError(
        f"Neither PLYM_TEST_MODE nor PLYM_TEST_BASE_URL is set. {_DESTRUCTIVE} "
        "Set PLYM_TEST_MODE=inprocess for a throwaway database, or PLYM_TEST_BASE_URL "
        "to the origin of a throwaway instance."
    )
if TEST_MODE not in TEST_MODES:
    raise RuntimeError(f"PLYM_TEST_MODE={TEST_MODE!r} is not one of {', '.join(TEST_MODES)}.")

if TEST_MODE == "inprocess":
    os.environ["PLYM_DB_HOST"] = os.environ.get("PLYM_TEST_DB_HOST", "localhost")
    os.environ["PLYM_DB_PORT"] = os.environ.get("PLYM_TEST_DB_PORT", "5433")
    os.environ["PLYM_DB_NAME"] = os.environ.get("PLYM_TEST_DB_NAME", "plym_test")
    os.environ["PLYM_DB_USER"] = os.environ.get("PLYM_TEST_DB_USER", "plym")
    os.environ["PLYM_DB_PASSWORD"] = os.environ.get("PLYM_TEST_DB_PASSWORD", "plym")
    os.environ["PLYM_CONFIG_PATH"] = os.environ.get("PLYM_TEST_CONFIG_PATH", "config.yaml")
    os.environ.setdefault("PLYM_SUPERUSER_EMAIL", "root@plym.local")
    os.environ.setdefault("PLYM_SUPERUSER_PASSWORD", "plym")
    os.environ.setdefault("PLYM_JWT_SECRET", "test-secret-inprocess-0123456789abcdef")
    os.environ.setdefault("PLYM_TRACE_EXPORTER", "none")
    _storage = Path(tempfile.mkdtemp(prefix="plym-test-storage-"))
    os.environ["PLYM_STORAGE_DIR"] = str(_storage)
    os.environ["PLYM_UPLOADS_DIR"] = str(_storage / "_uploads")
    os.environ["PLYM_GENERATED_DIR"] = str(_storage / ".generated")
    os.environ["PLYM_BACKUPS_DIR"] = str(_storage / "backups")
    os.environ["PLYM_FONTS_DIR"] = str(_storage / "webfonts")
    os.environ["PLYM_STATIC_DIR"] = str(_storage / "static")

    BASE_URL = "http://testserver"
    ADMIN_EMAIL = os.environ["PLYM_SUPERUSER_EMAIL"]
    ADMIN_PASSWORD = os.environ["PLYM_SUPERUSER_PASSWORD"]
else:
    BASE_URL = _env("PLYM_TEST_BASE_URL")
    if not BASE_URL:
        raise RuntimeError(
            f"PLYM_TEST_MODE is live but PLYM_TEST_BASE_URL is not set. {_DESTRUCTIVE} "
            "Set PLYM_TEST_BASE_URL to the origin of a throwaway instance."
        )
    ADMIN_EMAIL = _env("PLYM_TEST_ADMIN_EMAIL") or "root@plym.local"
    ADMIN_PASSWORD = _env("PLYM_TEST_ADMIN_PASSWORD") or "plym"


@pytest.fixture(scope="session", autouse=True)
def _provision_inprocess() -> Iterator[None]:
    if TEST_MODE != "inprocess":
        yield
        return

    from argon2 import PasswordHasher

    import plym.service.password_service as password_service

    password_service._hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)

    from plym.config.site import load_site_config
    from plym.db.migrate import apply_migrations
    from plym.db.session import dispose_engine
    from plym.main import app
    from plym.service.bootstrap import ensure_superuser
    from plym.settings import settings

    if "test" not in settings.db_name.lower():
        raise RuntimeError(
            f"refusing to migrate database {settings.db_name!r} on "
            f"{settings.db_host}:{settings.db_port}: the in-process suite owns and rewrites the "
            "schema of its database, so the name must identify it as a test database "
            "(it must contain 'test'). Set PLYM_TEST_DB_NAME."
        )

    async def _provision() -> None:
        await apply_migrations()
        await ensure_superuser()
        await dispose_engine()

    asyncio.run(_provision())
    app.state.site = load_site_config()
    app.state.settings = settings
    app.state.css = ""
    app.state.prism_js = ""
    yield


@pytest.fixture(autouse=True)
def _clear_render_cache() -> None:
    if TEST_MODE != "inprocess":
        return
    from plym.render.cache import get_store

    get_store().delete_prefix("")


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    if TEST_MODE != "inprocess":
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as c:
            yield c
        return

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from plym.api.deps import db_session
    from plym.main import app
    from plym.settings import settings

    engine = create_async_engine(settings.database_url)
    conn = await engine.connect()
    outer = await conn.begin()
    factory = async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

    async def _override_db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[db_session] = _override_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c
    finally:
        app.dependency_overrides.pop(db_session, None)
        await outer.rollback()
        await conn.close()
        await engine.dispose()


@pytest.fixture
async def admin_tokens(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


@pytest.fixture
async def auth_headers(admin_tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_tokens['access_token']}"}


@pytest.fixture
async def user_factory(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> AsyncIterator[Callable[..., Awaitable[dict[str, Any]]]]:
    created: list[int] = []

    async def _make(role: str = "reader", password: str = "factory-pw-12345") -> dict[str, Any]:
        email = f"factory-{uuid.uuid4().hex[:12]}@plym.local"
        created_resp = await client.post(
            "/api/users",
            json={"email": email, "password": password, "display_name": "Factory", "role": role},
            headers=auth_headers,
        )
        assert created_resp.status_code == 201, created_resp.text
        user_id = created_resp.json()["id"]
        created.append(user_id)
        login = await client.post("/api/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        return {
            "id": user_id,
            "email": email,
            "password": password,
            "role": role,
            "headers": {"Authorization": f"Bearer {token}"},
        }

    yield _make

    if TEST_MODE != "inprocess":
        for user_id in created:
            await client.delete(f"/api/users/{user_id}/deactivate", headers=auth_headers)


@pytest.fixture
def unique_slug() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (128, 64, 200)).save(buf, format="PNG")
    return buf.getvalue()

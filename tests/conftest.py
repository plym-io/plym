import asyncio
import io
import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import httpx
import pytest
from PIL import Image

TEST_MODE = os.environ.get("PLYM_TEST_MODE", "live")

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

BASE_URL = os.environ.get("PLYM_TEST_BASE_URL", "http://localhost:8000")
ADMIN_EMAIL = os.environ.get("PLYM_TEST_ADMIN_EMAIL", "root@plym.local")
ADMIN_PASSWORD = os.environ.get("PLYM_TEST_ADMIN_PASSWORD", "plym")


@pytest.fixture(scope="session", autouse=True)
def _provision_inprocess() -> AsyncIterator[None]:
    if TEST_MODE != "inprocess":
        yield
        return

    # Cheap argon2 params for tests: same process as the in-process app, so this also
    # speeds the app's own hashing. Auth semantics are unchanged (verify still works),
    # so the auth/role tests keep exercising real login — unlike a blanket auth override.
    import plym.service.password_service as password_service

    password_service._hasher = password_service.PasswordHasher(
        time_cost=1, memory_cost=8, parallelism=1
    )

    from plym.config.site import load_site_config
    from plym.db.migrate import apply_migrations
    from plym.db.session import dispose_engine
    from plym.main import app
    from plym.service.bootstrap import ensure_superuser
    from plym.settings import settings

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

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from plym.api.deps import db_session
    from plym.main import app
    from plym.settings import settings

    # One connection per test wrapped in an outer transaction that is always rolled
    # back. Sessions handed to the app join that transaction via savepoints, so the
    # services' own commit()s are released as savepoints (visible to later requests in
    # the same test) but undone at teardown — full isolation, no accumulation, no
    # per-request connection churn.
    engine = create_async_engine(settings.database_url)
    conn = await engine.connect()
    outer = await conn.begin()
    factory = async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

    async def _override_db() -> AsyncIterator:
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
async def admin_tokens(client: httpx.AsyncClient) -> dict:
    response = await client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
async def auth_headers(admin_tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_tokens['access_token']}"}


@pytest.fixture
async def user_factory(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> AsyncIterator[Callable[..., Awaitable[dict]]]:
    created: list[int] = []

    async def _make(role: str = "reader", password: str = "factory-pw-12345") -> dict:
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

    # In live mode there is no rollback, so deactivate created users to limit residue.
    # In inprocess mode the per-test transaction rollback already discards them.
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

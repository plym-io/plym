import io
import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from PIL import Image

BASE_URL = os.environ.get("PLYM_TEST_BASE_URL", "http://localhost:8000")
ADMIN_EMAIL = os.environ.get("PLYM_TEST_ADMIN_EMAIL", "root@plym.local")
ADMIN_PASSWORD = os.environ.get("PLYM_TEST_ADMIN_PASSWORD", "plym")


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as c:
        yield c


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
def unique_slug() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (128, 64, 200)).save(buf, format="PNG")
    return buf.getvalue()

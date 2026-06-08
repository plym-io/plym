import httpx
import pytest

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


@pytest.mark.asyncio
async def test_login_with_valid_credentials(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and len(body["access_token"]) > 20
    assert isinstance(body["refresh_token"], str) and len(body["refresh_token"]) > 20


@pytest.mark.asyncio
async def test_login_with_wrong_password(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": "definitely-wrong"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "auth.invalid_credentials"


@pytest.mark.asyncio
async def test_login_with_unknown_user(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/auth/login",
        json={"email": "nope@example.com", "password": "whatever"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_and_revokes_prior(
    client: httpx.AsyncClient, admin_tokens: dict
) -> None:
    old_refresh = admin_tokens["refresh_token"]
    r = await client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200
    new_pair = r.json()
    assert new_pair["refresh_token"] != old_refresh

    r2 = await client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401
    assert r2.json()["detail"]["code"] == "auth.token_invalid"


@pytest.mark.asyncio
async def test_me_requires_token(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/users/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_admin(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.get("/api/users/me", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == ADMIN_EMAIL
    assert body["role"] == "administrator"

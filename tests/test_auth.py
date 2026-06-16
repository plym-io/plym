from collections.abc import Awaitable, Callable

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
    assert r.json()["detail"]["code"] == "auth.invalid_credentials"


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
    assert r.json()["detail"]["code"] == "auth.token_invalid"


@pytest.mark.asyncio
async def test_me_returns_admin(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.get("/api/users/me", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == ADMIN_EMAIL
    assert body["role"] == "administrator"


@pytest.mark.asyncio
async def test_change_password_rotates_credentials(
    client: httpx.AsyncClient, user_factory: Callable[..., Awaitable[dict]]
) -> None:
    user = await user_factory()
    old_password = user["password"]
    new_password = "rotated-pw-67890"

    r = await client.post(
        "/api/auth/change-password",
        json={"old_password": old_password, "new_password": new_password},
        headers=user["headers"],
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    old_login = await client.post(
        "/api/auth/login", json={"email": user["email"], "password": old_password}
    )
    assert old_login.status_code == 401
    assert old_login.json()["detail"]["code"] == "auth.invalid_credentials"

    new_login = await client.post(
        "/api/auth/login", json={"email": user["email"], "password": new_password}
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_change_password_wrong_old_rejected(
    client: httpx.AsyncClient, user_factory: Callable[..., Awaitable[dict]]
) -> None:
    user = await user_factory()
    r = await client.post(
        "/api/auth/change-password",
        json={"old_password": "not-the-real-password", "new_password": "irrelevant-pw-123"},
        headers=user["headers"],
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "auth.invalid_credentials"


@pytest.mark.asyncio
async def test_change_password_requires_token(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/auth/change-password",
        json={"old_password": "whatever", "new_password": "newpassword-123"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "auth.token_invalid"


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(
    client: httpx.AsyncClient, user_factory: Callable[..., Awaitable[dict]]
) -> None:
    user = await user_factory()
    login = await client.post(
        "/api/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    out = await client.post("/api/auth/logout", json={"refresh_token": refresh_token})
    assert out.status_code == 200
    assert out.json() == {"ok": True}

    reuse = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse.status_code == 401
    assert reuse.json()["detail"]["code"] == "auth.token_invalid"

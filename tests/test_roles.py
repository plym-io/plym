from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest


@pytest.mark.asyncio
async def test_reader_cannot_create_post(
    client: httpx.AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, Any]]],
    unique_slug: str,
) -> None:
    reader = await user_factory(role="reader")
    r = await client.post(
        "/api/posts",
        json={"title": "nope", "slug": unique_slug, "content": "x"},
        headers=reader["headers"],
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "auth.insufficient_role"


@pytest.mark.asyncio
async def test_reader_can_read_config(
    client: httpx.AsyncClient, user_factory: Callable[..., Awaitable[dict[str, Any]]]
) -> None:
    reader = await user_factory(role="reader")
    r = await client.get("/api/config", headers=reader["headers"])
    assert r.status_code == 200
    assert r.json()["name"]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["reader", "editor"])
async def test_any_signed_in_role_can_list_users(
    client: httpx.AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, Any]]],
    role: str,
) -> None:
    actor = await user_factory(role=role)
    r = await client.get("/api/users", headers=actor["headers"])
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_listing_users_still_requires_signing_in(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/users")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["reader", "editor"])
async def test_non_admins_cannot_change_other_users(
    client: httpx.AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, Any]]],
    role: str,
) -> None:
    actor = await user_factory(role=role)
    target = await user_factory(role="reader")
    target_id = target["id"]

    created = await client.post(
        "/api/users",
        json={"email": "nope@plym.local", "display_name": "nope", "role": "reader"},
        headers=actor["headers"],
    )
    assert created.status_code == 403

    reset = await client.post(f"/api/users/{target_id}/reset-password", headers=actor["headers"])
    assert reset.status_code == 403

    deactivated = await client.delete(
        f"/api/users/{target_id}/deactivate", headers=actor["headers"]
    )
    assert deactivated.status_code == 403


@pytest.mark.asyncio
async def test_admin_promotes_a_reader_and_the_new_role_applies_at_once(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    user_factory: Callable[..., Awaitable[dict[str, Any]]],
    unique_slug: str,
) -> None:
    reader = await user_factory(role="reader")
    refused = await client.post(
        "/api/posts",
        json={"title": "nope", "slug": unique_slug, "content": "x"},
        headers=reader["headers"],
    )
    assert refused.status_code == 403

    promoted = await client.patch(
        f"/api/users/{reader['id']}/role", json={"role": "editor"}, headers=auth_headers
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["role"] == "editor"

    created = await client.post(
        "/api/posts",
        json={"title": "by promoted editor", "slug": unique_slug, "content": "x"},
        headers=reader["headers"],
    )
    assert created.status_code == 201, created.text
    await client.delete(f"/api/posts/{created.json()['id']}", headers=reader["headers"])


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["reader", "editor"])
async def test_non_admins_cannot_change_roles(
    client: httpx.AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, Any]]],
    role: str,
) -> None:
    actor = await user_factory(role=role)
    target = await user_factory(role="reader")
    r = await client.patch(
        f"/api/users/{target['id']}/role",
        json={"role": "administrator"},
        headers=actor["headers"],
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "auth.insufficient_role"


@pytest.mark.asyncio
async def test_admin_cannot_change_their_own_role(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    me = (await client.get("/api/users/me", headers=auth_headers)).json()
    r = await client.patch(
        f"/api/users/{me['id']}/role", json={"role": "reader"}, headers=auth_headers
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "users.cannot_change_own_role"


@pytest.mark.asyncio
async def test_changing_the_role_of_an_unknown_user_is_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.patch(
        "/api/users/99999999/role", json={"role": "editor"}, headers=auth_headers
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "users.not_found"


@pytest.mark.asyncio
async def test_unknown_role_is_rejected(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    user_factory: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    target = await user_factory(role="reader")
    r = await client.patch(
        f"/api/users/{target['id']}/role", json={"role": "root"}, headers=auth_headers
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_editor_can_read_config(
    client: httpx.AsyncClient, user_factory: Callable[..., Awaitable[dict[str, Any]]]
) -> None:
    editor = await user_factory(role="editor")
    r = await client.get("/api/config", headers=editor["headers"])
    assert r.status_code == 200
    assert r.json()["name"]


@pytest.mark.asyncio
async def test_editor_can_create_and_delete_post(
    client: httpx.AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, Any]]],
    unique_slug: str,
) -> None:
    editor = await user_factory(role="editor")
    created = await client.post(
        "/api/posts",
        json={"title": "by editor", "slug": unique_slug, "content": "x"},
        headers=editor["headers"],
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    deleted = await client.delete(f"/api/posts/{post_id}", headers=editor["headers"])
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_reader_cannot_refresh_every_post(
    client: httpx.AsyncClient, user_factory: Callable[..., Awaitable[dict[str, Any]]]
) -> None:
    reader = await user_factory(role="reader")
    r = await client.post("/api/posts/refresh-all", headers=reader["headers"])
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "auth.insufficient_role"

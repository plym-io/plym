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

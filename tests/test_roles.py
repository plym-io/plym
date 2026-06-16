from collections.abc import Awaitable, Callable

import httpx
import pytest


@pytest.mark.asyncio
async def test_reader_cannot_create_post(
    client: httpx.AsyncClient,
    user_factory: Callable[..., Awaitable[dict]],
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
    client: httpx.AsyncClient, user_factory: Callable[..., Awaitable[dict]]
) -> None:
    reader = await user_factory(role="reader")
    r = await client.get("/api/config", headers=reader["headers"])
    assert r.status_code == 200
    assert r.json()["name"]


@pytest.mark.asyncio
async def test_reader_can_list_users(
    client: httpx.AsyncClient, user_factory: Callable[..., Awaitable[dict]]
) -> None:
    reader = await user_factory(role="reader")
    r = await client.get("/api/users", headers=reader["headers"])
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_editor_can_read_config(
    client: httpx.AsyncClient, user_factory: Callable[..., Awaitable[dict]]
) -> None:
    editor = await user_factory(role="editor")
    r = await client.get("/api/config", headers=editor["headers"])
    assert r.status_code == 200
    assert r.json()["name"]


@pytest.mark.asyncio
async def test_editor_can_create_and_delete_post(
    client: httpx.AsyncClient,
    user_factory: Callable[..., Awaitable[dict]],
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

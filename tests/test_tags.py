import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest


@pytest.mark.asyncio
async def test_list_tags_is_public_and_shaped(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/tags")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    for item in body:
        assert set(item.keys()) == {"id", "name", "slug"}


@pytest.mark.asyncio
async def test_created_post_tag_appears_in_listing(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    tag_name = f"qa{uuid.uuid4().hex[:10]}"
    created = await client.post(
        "/api/posts",
        json={"title": "tagged", "slug": unique_slug, "content": "x", "tags": [tag_name]},
        headers=auth_headers,
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    try:
        r = await client.get("/api/tags")
        assert r.status_code == 200
        match = next((t for t in r.json() if t["name"] == tag_name), None)
        assert match is not None
        assert match["slug"] == tag_name
        assert isinstance(match["id"], int)
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_tags_are_alphabetical_and_carry_no_weight(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    base = uuid.uuid4().hex[:10]
    alpha_first, alpha_last = f"aa{base}", f"zz{base}"
    r = await client.post(
        "/api/posts",
        json={
            "title": "tagged",
            "slug": unique_slug,
            "content": "x",
            "tags": [alpha_last, alpha_first],
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    post_id = r.json()["id"]
    try:
        listing = (await client.get("/api/tags")).json()
        positions = {t["name"]: idx for idx, t in enumerate(listing)}
        assert positions[alpha_first] < positions[alpha_last]

        post = (await client.get(f"/api/posts/{post_id}", headers=auth_headers)).json()
        names = [t["name"] for t in post["tags"]]
        assert names.index(alpha_first) < names.index(alpha_last)
        assert all("weight" not in t for t in post["tags"])
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_tag_weight_endpoint_is_gone(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.patch("/api/tags/1", json={"weight": 1}, headers=auth_headers)
    assert r.status_code == 405


async def _tag_id(client: httpx.AsyncClient, name: str) -> int:
    listing = (await client.get("/api/tags")).json()
    match = next(t for t in listing if t["name"] == name)
    return int(match["id"])


@pytest.mark.asyncio
async def test_deleting_a_linked_tag_is_refused(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    tag_name = f"qa{uuid.uuid4().hex[:10]}"
    created = await client.post(
        "/api/posts",
        json={"title": "tagged", "slug": unique_slug, "content": "x", "tags": [tag_name]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    post_id = created.json()["id"]
    tag_id = await _tag_id(client, tag_name)
    try:
        r = await client.delete(f"/api/tags/{tag_id}", headers=auth_headers)
        assert r.status_code == 428, r.text
        assert r.json()["detail"]["code"] == "tags.in_use"
        assert await _tag_id(client, tag_name) == tag_id
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_unlinked_tag_is_deleted(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    tag_name = f"qa{uuid.uuid4().hex[:10]}"
    created = await client.post(
        "/api/posts",
        json={"title": "tagged", "slug": unique_slug, "content": "x", "tags": [tag_name]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    post_id = created.json()["id"]
    tag_id = await _tag_id(client, tag_name)
    await client.delete(f"/api/posts/{post_id}", headers=auth_headers)

    r = await client.delete(f"/api/tags/{tag_id}", headers=auth_headers)
    assert r.status_code == 204, r.text
    assert all(t["id"] != tag_id for t in (await client.get("/api/tags")).json())

    again = await client.delete(f"/api/tags/{tag_id}", headers=auth_headers)
    assert again.status_code == 404
    assert again.json()["detail"]["code"] == "tags.not_found"


@pytest.mark.asyncio
async def test_readers_cannot_delete_tags(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    user_factory: Callable[..., Awaitable[dict[str, Any]]],
    unique_slug: str,
) -> None:
    tag_name = f"qa{uuid.uuid4().hex[:10]}"
    created = await client.post(
        "/api/posts",
        json={"title": "tagged", "slug": unique_slug, "content": "x", "tags": [tag_name]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    post_id = created.json()["id"]
    tag_id = await _tag_id(client, tag_name)
    try:
        reader = await user_factory(role="reader")
        r = await client.delete(f"/api/tags/{tag_id}", headers=reader["headers"])
        assert r.status_code == 403
        assert (await client.delete(f"/api/tags/{tag_id}")).status_code == 401
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)

import uuid

import httpx
import pytest


@pytest.mark.asyncio
async def test_list_tags_is_public_and_shaped(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/tags")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    for item in body:
        assert {"id", "name", "slug"} <= set(item.keys())


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

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


@pytest.mark.asyncio
async def test_tag_weight_orders_listing_and_post_payload(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    base = uuid.uuid4().hex[:10]
    alpha_first, alpha_last = f"aa{base}", f"zz{base}"
    r = await client.post(
        "/api/posts",
        json={
            "title": "sectioned",
            "slug": unique_slug,
            "content": "x",
            "tags": [alpha_first, alpha_last],
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    post_id = r.json()["id"]
    try:
        listing = (await client.get("/api/tags")).json()
        ids = {t["name"]: t["id"] for t in listing if t["name"] in (alpha_first, alpha_last)}
        assert len(ids) == 2

        r = await client.patch(
            f"/api/tags/{ids[alpha_last]}", json={"weight": 1}, headers=auth_headers
        )
        assert r.status_code == 200
        assert r.json()["weight"] == 1
        r = await client.patch(
            f"/api/tags/{ids[alpha_first]}", json={"weight": 2}, headers=auth_headers
        )
        assert r.status_code == 200

        listing = (await client.get("/api/tags")).json()
        positions = {t["name"]: idx for idx, t in enumerate(listing)}
        assert positions[alpha_last] < positions[alpha_first]

        post = (await client.get(f"/api/posts/{post_id}", headers=auth_headers)).json()
        names = [t["name"] for t in post["tags"]]
        assert names.index(alpha_last) < names.index(alpha_first)
        assert all("weight" in t for t in post["tags"])

        r = await client.patch(
            f"/api/tags/{ids[alpha_last]}", json={"weight": None}, headers=auth_headers
        )
        assert r.status_code == 200
        assert r.json()["weight"] is None
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_tag_patch_requires_editor(client: httpx.AsyncClient, user_factory) -> None:
    reader = await user_factory(role="reader")
    r = await client.patch("/api/tags/1", json={"weight": 1}, headers=reader["headers"])
    assert r.status_code == 403

    r = await client.patch("/api/tags/1", json={"weight": 1})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_tag_patch_unknown_id_returns_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.patch("/api/tags/99999999", json={"weight": 1}, headers=auth_headers)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "tags.not_found"

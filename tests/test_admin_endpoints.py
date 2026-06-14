import httpx
import pytest


@pytest.mark.asyncio
async def test_get_config_requires_admin(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/config")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_config_returns_site_settings(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.get("/api/config", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["name"]
    assert body["blog_prefix"] in ("", "/blog")
    assert "fonts" in body and "colors" in body


@pytest.mark.asyncio
async def test_list_users_requires_admin(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/users")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_users_returns_paginated(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.get("/api/users", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["page"] == 1
    assert body["total"] >= 1
    assert any(u["role"] == "administrator" for u in body["items"])


@pytest.mark.asyncio
async def test_posts_include_drafts_requires_editor(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={"title": "draft", "slug": unique_slug, "content": "x"},
        headers=auth_headers,
    )
    post_id = r.json()["id"]
    try:
        r = await client.get("/api/posts", params={"include_drafts": True})
        assert r.status_code == 403

        r = await client.get(
            "/api/posts", headers=auth_headers, params={"include_drafts": True}
        )
        assert r.status_code == 200
        assert any(p["slug"] == unique_slug for p in r.json()["items"])

        r = await client.get(
            "/api/posts", headers=auth_headers, params={"status": "draft"}
        )
        assert r.status_code == 200
        assert all(p["status"] == "draft" for p in r.json()["items"])
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_get_draft_post_hidden_from_public(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={"title": "hidden draft", "slug": unique_slug, "content": "x"},
        headers=auth_headers,
    )
    post_id = r.json()["id"]
    try:
        r = await client.get(f"/api/posts/{post_id}")
        assert r.status_code == 404

        r = await client.get(f"/api/posts/{post_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "draft"
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)

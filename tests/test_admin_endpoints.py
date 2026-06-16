import uuid

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


@pytest.mark.asyncio
async def test_deactivate_user_requires_admin(client: httpx.AsyncClient) -> None:
    r = await client.delete("/api/users/1")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_self(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    me = await client.get("/api/users/me", headers=auth_headers)
    assert me.status_code == 200
    r = await client.delete(f"/api/users/{me.json()['id']}", headers=auth_headers)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "users.cannot_delete_self"


@pytest.mark.asyncio
async def test_deactivate_missing_user_returns_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.delete("/api/users/999999999", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_deactivate_then_reactivate_user(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    email = f"deact-{uuid.uuid4().hex[:12]}@plym.local"
    password = "deactivate-pw-123"
    created = await client.post(
        "/api/users",
        json={"email": email, "password": password, "display_name": "Deact", "role": "reader"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    creds = {"email": email, "password": password}

    assert (await client.post("/api/auth/login", json=creds)).status_code == 200

    deactivated = await client.delete(f"/api/users/{user_id}", headers=auth_headers)
    assert deactivated.status_code == 204

    blocked = await client.post("/api/auth/login", json=creds)
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "auth.inactive_user"

    listing = await client.get("/api/users", headers=auth_headers)
    target = next(u for u in listing.json()["items"] if u["id"] == user_id)
    assert target["is_active"] is False

    reactivated = await client.post(f"/api/users/{user_id}/reactivate", headers=auth_headers)
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True

    assert (await client.post("/api/auth/login", json=creds)).status_code == 200

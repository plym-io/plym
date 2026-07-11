import httpx
import pytest


@pytest.mark.asyncio
async def test_patch_me_sets_and_returns_links(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    links = [
        {"type": "github", "url": "https://github.com/example"},
        {"type": "website", "url": "https://example.com"},
    ]
    r = await client.patch("/api/users/me", json={"links": links}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["links"] == links

    me = await client.get("/api/users/me", headers=auth_headers)
    assert me.status_code == 200
    assert me.json()["links"] == links


@pytest.mark.asyncio
async def test_patch_me_rejects_non_http_url(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.patch(
        "/api/users/me",
        json={"links": [{"type": "github", "url": "javascript:alert(1)"}]},
        headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_me_rejects_empty_type(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.patch(
        "/api/users/me",
        json={"links": [{"type": "", "url": "https://example.com"}]},
        headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_omitting_links_preserves_existing(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    links = [{"type": "x", "url": "https://x.com/example"}]
    await client.patch("/api/users/me", json={"links": links}, headers=auth_headers)

    r = await client.patch(
        "/api/users/me", json={"display_name": "Renamed"}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "Renamed"
    assert r.json()["links"] == links


@pytest.mark.asyncio
async def test_empty_list_clears_links(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    await client.patch(
        "/api/users/me",
        json={"links": [{"type": "github", "url": "https://github.com/example"}]},
        headers=auth_headers,
    )
    r = await client.patch("/api/users/me", json={"links": []}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["links"] == []


@pytest.mark.asyncio
async def test_post_author_carries_links(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    links = [{"type": "github", "url": "https://github.com/example"}]
    await client.patch("/api/users/me", json={"links": links}, headers=auth_headers)

    r = await client.post(
        "/api/posts",
        json={"title": "Author links", "slug": unique_slug, "content": "body"},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    post_id = r.json()["id"]
    try:
        assert r.json()["author"]["links"] == links
        listed = await client.get(
            "/api/posts", params={"include_drafts": "true"}, headers=auth_headers
        )
        assert listed.status_code == 200
        item = next(p for p in listed.json()["items"] if p["id"] == post_id)
        assert item["author"]["links"] == links
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)

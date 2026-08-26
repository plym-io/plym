import uuid

import httpx
import pytest

from tests.conftest import TEST_MODE


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
    me = (await client.get("/api/users/me", headers=auth_headers)).json()
    links = [{"type": "x", "url": "https://x.com/example"}]
    await client.patch("/api/users/me", json={"links": links}, headers=auth_headers)
    try:
        renamed = f"Renamed {uuid.uuid4().hex[:8]}"
        r = await client.patch(
            "/api/users/me", json={"display_name": renamed}, headers=auth_headers
        )
        assert r.status_code == 200
        assert r.json()["display_name"] == renamed
        assert r.json()["links"] == links
    finally:
        await client.patch(
            "/api/users/me",
            json={"display_name": me["display_name"], "links": me["links"]},
            headers=auth_headers,
        )


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


async def _publish_post(client: httpx.AsyncClient, auth_headers: dict[str, str], slug: str) -> int:
    created = await client.post(
        "/api/posts",
        json={"title": "profile sweep", "slug": slug, "content": "body"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    post_id = int(created.json()["id"])
    published = await client.patch(
        f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
    )
    assert published.status_code == 200, published.text
    return post_id


@pytest.mark.asyncio
async def test_rename_rerenders_published_posts(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    original = (await client.get("/api/users/me", headers=auth_headers)).json()["display_name"]
    post_id = await _publish_post(client, auth_headers, unique_slug)
    try:
        renamed = f"Renamed {uuid.uuid4().hex[:8]}"
        r = await client.patch(
            "/api/users/me", json={"display_name": renamed}, headers=auth_headers
        )
        assert r.status_code == 200, r.text

        served = await client.get(f"/{unique_slug}")
        assert served.status_code == 200, served.text
        assert renamed in served.text
    finally:
        await client.patch("/api/users/me", json={"display_name": original}, headers=auth_headers)
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_link_change_rerenders_published_posts(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    post_id = await _publish_post(client, auth_headers, unique_slug)
    try:
        url = f"https://github.com/{uuid.uuid4().hex[:8]}"
        r = await client.patch(
            "/api/users/me",
            json={"links": [{"type": "github", "url": url}]},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text

        served = await client.get(f"/{unique_slug}")
        assert served.status_code == 200, served.text
        assert f'"sameAs": ["{url}"]' in served.text
    finally:
        await client.patch("/api/users/me", json={"links": []}, headers=auth_headers)
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_bio_change_leaves_rendered_posts_untouched(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    if TEST_MODE != "inprocess":
        pytest.skip("needs direct access to the generated dir to observe the rendered file")
    from plym.settings import settings

    post_id = await _publish_post(client, auth_headers, unique_slug)
    try:
        rendered = settings.generated_dir / f"{unique_slug}.html"
        before = rendered.stat().st_mtime_ns

        r = await client.patch(
            "/api/users/me",
            json={"bio": f"Bio {uuid.uuid4().hex[:8]}"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert rendered.stat().st_mtime_ns == before
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)

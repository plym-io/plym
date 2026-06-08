import httpx
import pytest


@pytest.mark.asyncio
async def test_create_publish_refresh_serve_delete(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    payload = {
        "title": "Test post",
        "slug": unique_slug,
        "content": "# Heading\n\nSome body text.",
        "excerpt": "an excerpt",
    }
    r = await client.post("/api/posts", json=payload, headers=auth_headers)
    assert r.status_code == 201, r.text
    post = r.json()
    post_id = post["id"]
    assert post["status"] == "draft"
    assert post["published_at"] is None
    assert post["reading_time"] >= 1

    try:
        r = await client.patch(
            f"/api/posts/{post_id}",
            json={"status": "published"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "published"
        assert r.json()["published_at"] is not None

        r = await client.post(f"/api/posts/{post_id}/refresh", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["rendered_path"]

        r = await client.get(f"/blog/{unique_slug}")
        assert r.status_code == 200
        assert "<html" in r.text.lower()
        assert "Test post" in r.text
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_duplicate_slug_returns_409(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={"title": "first", "slug": unique_slug, "content": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    post_id = r.json()["id"]
    try:
        r2 = await client.post(
            "/api/posts",
            json={"title": "second", "slug": unique_slug, "content": "y"},
            headers=auth_headers,
        )
        assert r2.status_code == 409
        assert r2.json()["detail"]["code"] == "posts.slug_conflict"
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_invalid_slug_format_rejected(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.post(
        "/api/posts",
        json={"title": "bad", "slug": "Has Spaces!", "content": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_clear_cover_with_null(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={
            "title": "with cover",
            "slug": unique_slug,
            "content": "x",
            "cover": "https://example.com/img.jpg",
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    post_id = r.json()["id"]
    assert r.json()["cover"] == "https://example.com/img.jpg"

    try:
        r2 = await client.patch(
            f"/api/posts/{post_id}",
            json={"cover": None},
            headers=auth_headers,
        )
        assert r2.status_code == 200
        assert r2.json()["cover"] is None
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_canonical_url_round_trips(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    target = "https://medium.com/@me/original-2026-05"
    r = await client.post(
        "/api/posts",
        json={
            "title": "syndicated",
            "slug": unique_slug,
            "content": "# hi",
            "canonical_url": target,
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    post_id = r.json()["id"]
    try:
        assert r.json()["canonical_url"] == target

        r2 = await client.patch(
            f"/api/posts/{post_id}",
            json={"canonical_url": None},
            headers=auth_headers,
        )
        assert r2.json()["canonical_url"] is None

        r3 = await client.patch(
            f"/api/posts/{post_id}",
            json={"canonical_url": target},
            headers=auth_headers,
        )
        assert r3.json()["canonical_url"] == target
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_canonical_url_rejects_non_url(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={"title": "bad", "slug": unique_slug, "content": "x", "canonical_url": "not-a-url"},
        headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_canonical_url_appears_in_rendered_html(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    target = "https://example.com/original-source"
    r = await client.post(
        "/api/posts",
        json={
            "title": "canonical-render",
            "slug": unique_slug,
            "content": "# hi",
            "canonical_url": target,
        },
        headers=auth_headers,
    )
    post_id = r.json()["id"]
    try:
        await client.patch(
            f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
        )
        await client.post(f"/api/posts/{post_id}/refresh", headers=auth_headers)
        served = await client.get(f"/blog/{unique_slug}")
        assert served.status_code == 200
        assert f'rel="canonical" href="{target}"' in served.text
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_unpublish_removes_rendered_file(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={"title": "ephemeral", "slug": unique_slug, "content": "# hi"},
        headers=auth_headers,
    )
    post_id = r.json()["id"]
    try:
        await client.patch(
            f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
        )
        await client.post(f"/api/posts/{post_id}/refresh", headers=auth_headers)
        r = await client.get(f"/blog/{unique_slug}")
        assert r.status_code == 200

        await client.patch(
            f"/api/posts/{post_id}", json={"status": "draft"}, headers=auth_headers
        )
        r = await client.get(f"/blog/{unique_slug}")
        assert r.status_code == 404
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)

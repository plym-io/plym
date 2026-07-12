import httpx
import pytest

from tests.conftest import BASE_URL, TEST_MODE


@pytest.mark.asyncio
async def test_index_returns_html(client: httpx.AsyncClient) -> None:
    r = await client.get("/blog/")
    assert r.status_code == 200
    assert "<html" in r.text.lower()
    assert "cache-control" in {k.lower() for k in r.headers}


@pytest.mark.asyncio
async def test_root_redirects_to_blog_home(client: httpx.AsyncClient) -> None:
    r = await client.get("/", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"] == "https://plym.local/blog/"


@pytest.mark.asyncio
async def test_blog_missing_slug_404(client: httpx.AsyncClient) -> None:
    r = await client.get("/blog/this-slug-does-not-exist-anywhere")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cache_control_on_post(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={"title": "cached", "slug": unique_slug, "content": "# x"},
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
        assert "max-age=" in r.headers.get("cache-control", "")
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.skipif(
    TEST_MODE == "inprocess",
    reason="gzip content-negotiation is a server/proxy concern, not exercisable in-process",
)
@pytest.mark.asyncio
async def test_gzip_negotiation() -> None:
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=10.0,
        headers={"Accept-Encoding": "gzip"},
    ) as c:
        r = await c.get("/blog/")
        assert r.status_code == 200
        assert r.headers.get("content-encoding") == "gzip"
        assert "accept-encoding" in r.headers.get("vary", "").lower()


@pytest.mark.asyncio
async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

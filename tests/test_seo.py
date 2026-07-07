import httpx
import pytest


@pytest.mark.asyncio
async def test_sitemap_xml(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={"title": "Sitemap fixture", "slug": unique_slug, "content": "body"},
        headers=auth_headers,
    )
    post_id = r.json()["id"]
    try:
        await client.patch(
            f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
        )

        r = await client.get("/sitemap.xml")
        assert r.status_code == 200
        assert "application/xml" in r.headers["content-type"]
        body = r.text
        assert "<urlset" in body
        assert f"<loc>https://plym.local/blog/{unique_slug}</loc>" in body
        assert f"/blog/blog/{unique_slug}" not in body
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_llms_txt(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={
            "title": "Llms fixture",
            "slug": unique_slug,
            "content": "body",
            "excerpt": "About the fixture",
        },
        headers=auth_headers,
    )
    post_id = r.json()["id"]
    try:
        await client.patch(
            f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
        )

        r = await client.get("/llms.txt")
        assert r.status_code == 200
        assert "text/markdown" in r.headers["content-type"]
        body = r.text
        assert body.startswith("# Plym")
        assert "## Posts" in body
        assert (
            f"- [Llms fixture](https://plym.local/blog/{unique_slug}): About the fixture" in body
        )
        assert f"/blog/blog/{unique_slug}" not in body

        r = await client.get("/blog/llms.txt")
        assert r.status_code == 200
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_robots_txt(client: httpx.AsyncClient) -> None:
    r = await client.get("/robots.txt")
    assert r.status_code == 200
    body = r.text
    assert body.startswith("User-agent: *")
    assert "Disallow: /api/" in body
    assert "Sitemap:" in body
    assert "/sitemap.xml" in body

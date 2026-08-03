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
        assert f"<loc>https://plym.local/{unique_slug}</loc>" in body
        assert f"/blog/{unique_slug}" not in body
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
        assert f"- [Llms fixture](https://plym.local/{unique_slug}): About the fixture" in body
        assert f"/blog/{unique_slug}" not in body

        r = await client.get("/llms.txt")
        assert r.status_code == 200
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_llms_txt_lists_the_homepage(client: httpx.AsyncClient) -> None:
    r = await client.get("/llms.txt")
    assert r.status_code == 200
    body = r.text
    assert "- [Plym](https://plym.local/)" in body
    if "## Posts" in body:
        assert body.index("- [Plym](https://plym.local/)") < body.index("## Posts")


def test_llms_body_omits_posts_heading_without_entries() -> None:
    from plym.api.seo_router import _llms_body
    from plym.config.site import SiteConfig

    site = SiteConfig(name="Plym", description="A CMS", blog_home="plym.local")
    body = _llms_body(site, site.public_blog_url(), [])
    assert "## Posts" not in body
    assert body == "# Plym\n\n> A CMS\n\n- [Plym](https://plym.local/)\n"

    body = _llms_body(site, site.public_blog_url(), ["- [One](https://plym.local/one)"])
    assert "## Posts\n\n- [One](https://plym.local/one)\n" in body


@pytest.mark.asyncio
async def test_llms_txt_escapes_excerpt_markdown(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={
            "title": "Escape (fixture) [x]",
            "slug": unique_slug,
            "content": "body",
            "excerpt": "Closes ) and ] and opens ( and [",
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
        body = r.text
        assert (
            f"- [Escape \\(fixture\\) \\[x\\]](https://plym.local/{unique_slug}): "
            "Closes \\) and \\] and opens \\( and \\[" in body
        )
        assert "Closes ) and ] and opens ( and [" not in body
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_rendered_html_points_at_llms_txt(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    pointer = '<link rel="alternate" type="text/markdown" href="https://plym.local/llms.txt">'
    r = await client.post(
        "/api/posts",
        json={"title": "Llms pointer", "slug": unique_slug, "content": "body"},
        headers=auth_headers,
    )
    post_id = r.json()["id"]
    try:
        await client.patch(
            f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
        )
        await client.post(f"/api/posts/{post_id}/refresh", headers=auth_headers)

        r = await client.get(f"/{unique_slug}")
        assert r.status_code == 200
        assert pointer in r.text

        r = await client.get("/")
        assert r.status_code == 200
        assert pointer in r.text
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

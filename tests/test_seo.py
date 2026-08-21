import json
import re

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
    from plym.config.site import SiteConfig
    from plym.service.site_files_service import _llms_body

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


_SKIPPED_BLOCKS = (
    "# Fixture heading\n\n"
    "```bash\nnpm run build\n```\n\n"
    "Plym writes every post to disk so the web server never runs Python."
)
_DERIVED = "Plym writes every post to disk so the web server never runs Python."


async def _publish_without_excerpt(
    client: httpx.AsyncClient, auth_headers: dict[str, str], slug: str
) -> int:
    created = await client.post(
        "/api/posts",
        json={"title": "Excerptless", "slug": slug, "content": _SKIPPED_BLOCKS},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    post_id: int = created.json()["id"]
    published = await client.patch(
        f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
    )
    assert published.status_code == 200, published.text
    return post_id


@pytest.mark.asyncio
async def test_a_post_without_an_excerpt_describes_itself_from_its_content(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    post_id = await _publish_without_excerpt(client, auth_headers, unique_slug)
    try:
        served = await client.get(f"/{unique_slug}")
        assert served.status_code == 200, served.text
        assert f'<meta name="description" content="{_DERIVED}">' in served.text
        assert f'<meta property="og:description" content="{_DERIVED}">' in served.text
        assert f'<meta name="twitter:description" content="{_DERIVED}">' in served.text

        scripts = re.findall(
            r'<script type="application/ld\+json">(.+?)</script>', served.text, re.DOTALL
        )
        article = next(
            payload
            for payload in (json.loads(script) for script in scripts)
            if payload.get("@type") == "BlogPosting"
        )
        assert article["description"] == _DERIVED
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_a_derived_excerpt_reaches_every_listing_surface(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    post_id = await _publish_without_excerpt(client, auth_headers, unique_slug)
    try:
        entry = f"- [Excerptless](https://plym.local/{unique_slug}): {_DERIVED}"

        llms = await client.get("/llms.txt")
        assert llms.status_code == 200
        assert entry in llms.text

        index = await client.get("/")
        assert index.status_code == 200
        assert f'<p class="plym-card-excerpt">{_DERIVED}</p>' in index.text

        index_markdown = await client.get("/", headers={"Accept": "text/markdown"})
        assert index_markdown.status_code == 200
        assert entry in index_markdown.text

        listed = await client.get("/api/posts", params={"page_size": 200})
        assert listed.status_code == 200
        item = next(p for p in listed.json()["items"] if p["slug"] == unique_slug)
        assert item["excerpt"] == _DERIVED

        built = await client.post("/api/index", headers=auth_headers)
        assert built.status_code == 200, built.text
        documents = (await client.get("/index.json")).json()["documents"]
        document = next(d for d in documents if d["slug"] == unique_slug)
        assert document["excerpt"] == _DERIVED
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_a_derived_excerpt_is_not_written_back_to_the_post(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    post_id = await _publish_without_excerpt(client, auth_headers, unique_slug)
    try:
        stored = await client.get(f"/api/posts/{post_id}", headers=auth_headers)
        assert stored.status_code == 200, stored.text
        assert stored.json()["excerpt"] is None

        rewritten = await client.patch(
            f"/api/posts/{post_id}",
            json={"content": "A rewritten opening paragraph."},
            headers=auth_headers,
        )
        assert rewritten.status_code == 200, rewritten.text

        served = await client.get(f"/{unique_slug}")
        assert served.status_code == 200
        assert '<meta name="description" content="A rewritten opening paragraph.">' in served.text
        assert _DERIVED not in served.text
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

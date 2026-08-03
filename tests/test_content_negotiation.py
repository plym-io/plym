import httpx
import pytest


async def _publish(client: httpx.AsyncClient, headers: dict[str, str], slug: str) -> int:
    created = await client.post(
        "/api/posts",
        headers=headers,
        json={
            "title": "Negotiated",
            "slug": slug,
            "content": "First paragraph.\n\n## Heading\n\nSecond paragraph.\n",
        },
    )
    assert created.status_code == 201
    post_id: int = created.json()["id"]
    published = await client.patch(
        f"/api/posts/{post_id}", headers=headers, json={"status": "published"}
    )
    assert published.status_code == 200
    return post_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "accept",
    [
        "text/markdown",
        "text/markdown, text/html",
        "text/html, text/markdown",
        "text/markdown;q=0.9",
        "text/plain, text/markdown;q=0.8",
        "text/html,text/markdown",
    ],
)
async def test_markdown_is_served_for_accept_variants(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    unique_slug: str,
    accept: str,
) -> None:
    post_id = await _publish(client, auth_headers, unique_slug)
    try:
        r = await client.get(f"/{unique_slug}", headers={"Accept": accept})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert "<html" not in r.text.lower()
        assert "accept" in r.headers.get("vary", "").lower()
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
@pytest.mark.parametrize("accept", ["text/html", "*/*", "application/json"])
async def test_html_is_served_when_markdown_not_requested(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    unique_slug: str,
    accept: str,
) -> None:
    post_id = await _publish(client, auth_headers, unique_slug)
    try:
        r = await client.get(f"/{unique_slug}", headers={"Accept": accept})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert "<html" in r.text.lower()
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_publishing_renders_without_an_explicit_refresh(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    post_id = await _publish(client, auth_headers, unique_slug)
    try:
        r = await client.get(f"/{unique_slug}")
        assert r.status_code == 200
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_markdown_suffix_serves_the_markdown_artifact(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    post_id = await _publish(client, auth_headers, unique_slug)
    try:
        r = await client.get(f"/{unique_slug}.md")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert "<html" not in r.text.lower()

        html = await client.get(f"/{unique_slug}")
        assert html.headers["content-type"].startswith("text/html")
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_markdown_suffix_for_an_unknown_post_is_not_found(
    client: httpx.AsyncClient, unique_slug: str
) -> None:
    r = await client.get(f"/{unique_slug}.md")
    assert r.status_code == 404

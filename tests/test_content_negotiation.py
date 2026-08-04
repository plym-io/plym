import uuid
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from tests.conftest import TEST_MODE


@pytest.fixture
def md_urls() -> Iterator[Callable[[bool], None]]:
    if TEST_MODE != "inprocess":
        pytest.skip("flipping md_urls needs in-process access to the site config")
    from plym.main import app

    previous = app.state.site.md_urls.enabled

    def _set(enabled: bool) -> None:
        app.state.site.md_urls.enabled = enabled

    try:
        yield _set
    finally:
        app.state.site.md_urls.enabled = previous


async def _publish(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    slug: str,
    category_id: int | None = None,
) -> int:
    payload: dict[str, Any] = {
        "title": "Negotiated",
        "slug": slug,
        "content": "First paragraph.\n\n## Heading\n\nSecond paragraph.\n",
    }
    if category_id is not None:
        payload["category_id"] = category_id
    created = await client.post("/api/posts", headers=headers, json=payload)
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
        assert "accept" in r.headers.get("vary", "").lower()
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
async def test_markdown_suffix_serves_the_markdown_artifact_when_enabled(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    unique_slug: str,
    md_urls: Callable[[bool], None],
) -> None:
    md_urls(True)
    post_id = await _publish(client, auth_headers, unique_slug)
    try:
        r = await client.get(f"/{unique_slug}.md")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert "<html" not in r.text.lower()

        negotiated = await client.get(f"/{unique_slug}", headers={"Accept": "text/markdown"})
        assert negotiated.status_code == 200
        assert negotiated.headers["content-type"].startswith("text/markdown")

        html = await client.get(f"/{unique_slug}")
        assert html.headers["content-type"].startswith("text/html")
        assert "accept" in html.headers.get("vary", "").lower()
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_categorised_markdown_suffix_serves_the_markdown_artifact_when_enabled(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    unique_slug: str,
    md_urls: Callable[[bool], None],
) -> None:
    md_urls(True)
    category = await client.post(
        "/api/categories", headers=auth_headers, json={"name": f"MD {uuid.uuid4().hex[:10]}"}
    )
    assert category.status_code == 201, category.text
    slug = category.json()["slug"]
    post_id = await _publish(client, auth_headers, unique_slug, category.json()["id"])
    try:
        r = await client.get(f"/{slug}/{unique_slug}.md")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert "<html" not in r.text.lower()
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)
        await client.delete(f"/api/categories/{category.json()['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_markdown_suffix_is_not_found_when_disabled(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    unique_slug: str,
    md_urls: Callable[[bool], None],
) -> None:
    md_urls(False)
    category = await client.post(
        "/api/categories", headers=auth_headers, json={"name": f"MD {uuid.uuid4().hex[:10]}"}
    )
    assert category.status_code == 201, category.text
    slug = category.json()["slug"]
    post_id = await _publish(client, auth_headers, unique_slug, category.json()["id"])
    try:
        assert (await client.get(f"/{unique_slug}.md")).status_code == 404
        assert (await client.get(f"/{slug}/{unique_slug}.md")).status_code == 404

        negotiated = await client.get(f"/{slug}/{unique_slug}", headers={"Accept": "text/markdown"})
        assert negotiated.status_code == 200
        assert negotiated.headers["content-type"].startswith("text/markdown")

        html = await client.get(f"/{slug}/{unique_slug}")
        assert html.headers["content-type"].startswith("text/html")
        assert "accept" in html.headers.get("vary", "").lower()
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)
        await client.delete(f"/api/categories/{category.json()['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_markdown_suffix_for_an_unknown_post_is_not_found(
    client: httpx.AsyncClient, unique_slug: str, md_urls: Callable[[bool], None]
) -> None:
    md_urls(True)
    r = await client.get(f"/{unique_slug}.md")
    assert r.status_code == 404

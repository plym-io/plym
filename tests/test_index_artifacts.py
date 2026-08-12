from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest

from plym.render.urls import index_path, index_url, is_index_path
from tests.conftest import TEST_MODE


def _artifact(relative: str, suffix: str) -> str:
    if TEST_MODE != "inprocess":
        pytest.skip("reads .generated/ directly, so it needs the in-process app")
    from plym.settings import settings

    target = settings.generated_dir / f"{relative}{suffix}"
    return target.read_text(encoding="utf-8") if target.exists() else ""


@pytest.fixture
async def published_posts(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> AsyncIterator[Callable[[int], Any]]:
    created: list[int] = []

    async def _make(count: int) -> list[dict[str, Any]]:
        import uuid

        posts: list[dict[str, Any]] = []
        for n in range(count):
            slug = f"test-index-{uuid.uuid4().hex[:12]}"
            r = await client.post(
                "/api/posts",
                json={"title": f"Index fixture {n}", "slug": slug, "content": "body"},
                headers=auth_headers,
            )
            assert r.status_code == 201, r.text
            post_id = r.json()["id"]
            created.append(post_id)
            published = await client.patch(
                f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
            )
            assert published.status_code == 200, published.text
            posts.append({"id": post_id, "slug": slug})
        return posts

    yield _make

    for post_id in created:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


def test_index_paths_and_urls() -> None:
    assert index_path(1) == "index"
    assert index_path(2) == "page/2"
    assert index_url("", 1) == "/"
    assert index_url("", 3) == "/page/3"
    assert index_url("/blog", 1) == "/blog/"
    assert index_url("/blog", 3) == "/blog/page/3"
    assert is_index_path("index")
    assert is_index_path("page/2")
    assert not is_index_path("hello")
    assert not is_index_path("notes/hello")


@pytest.mark.asyncio
async def test_publishing_writes_the_index_as_an_artifact(
    published_posts: Callable[[int], Any],
) -> None:
    posts = await published_posts(1)
    assert posts[0]["slug"] in _artifact(index_path(1), ".html")
    assert posts[0]["slug"] in _artifact(index_path(1), ".md")


@pytest.mark.asyncio
async def test_query_pagination_redirects_onto_the_path_form(
    client: httpx.AsyncClient,
) -> None:
    redirect = await client.get("/", params={"page": 2}, follow_redirects=False)
    assert redirect.status_code == 308
    assert redirect.headers["location"].endswith("/page/2")

    first = await client.get("/", params={"page": 1}, follow_redirects=False)
    assert first.status_code == 308
    assert first.headers["location"].endswith("/")

    page_one = await client.get("/page/1", follow_redirects=False)
    assert page_one.status_code == 308
    assert page_one.headers["location"].endswith("/")


@pytest.mark.asyncio
async def test_paged_indexes_become_artifacts_and_are_pruned(
    client: httpx.AsyncClient, auth_headers: dict[str, str], published_posts: Callable[[int], Any]
) -> None:
    if TEST_MODE != "inprocess":
        pytest.skip("moves the running site config, so it only runs against the in-process app")

    from plym.main import app

    site = app.state.site
    previous = site.pagination.page_size
    site.pagination.page_size = 1
    try:
        posts = await published_posts(3)
        # Newest first, so page 1 holds the last one published.
        assert posts[-1]["slug"] in _artifact(index_path(1), ".html")
        assert posts[-2]["slug"] in _artifact(index_path(2), ".html")
        assert posts[-3]["slug"] in _artifact(index_path(3), ".html")

        served = await client.get("/page/2")
        assert served.status_code == 200
        assert served.headers["cache-control"] == "public, max-age=60"
        assert posts[-2]["slug"] in served.text

        markdown = await client.get("/page/2", headers={"Accept": "text/markdown"})
        assert markdown.status_code == 200
        assert markdown.headers["content-type"].startswith("text/markdown")
        assert posts[-2]["slug"] in markdown.text

        # Three posts now fit on one page, so pages 2 and 3 must stop existing.
        site.pagination.page_size = 3
        repaginate = await client.patch(
            f"/api/posts/{posts[0]['id']}", json={"title": "Repaginate"}, headers=auth_headers
        )
        assert repaginate.status_code == 200, repaginate.text
        assert posts[-1]["slug"] in _artifact(index_path(1), ".html")
        assert _artifact(index_path(2), ".html") == ""
        assert _artifact(index_path(3), ".html") == ""
        assert (await client.get("/page/2")).status_code == 404
    finally:
        site.pagination.page_size = previous


@pytest.mark.asyncio
async def test_the_index_is_available_as_markdown(
    client: httpx.AsyncClient, published_posts: Callable[[int], Any]
) -> None:
    posts = await published_posts(1)

    markdown = await client.get("/", headers={"Accept": "text/markdown"})
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert posts[0]["slug"] in markdown.text
    assert "accept" in markdown.headers.get("vary", "").lower()

    html = await client.get("/")
    assert html.headers["content-type"].startswith("text/html")


@pytest.mark.asyncio
async def test_a_paged_index_declares_its_own_canonical(
    client: httpx.AsyncClient, published_posts: Callable[[int], Any]
) -> None:
    if TEST_MODE != "inprocess":
        pytest.skip("moves the running site config, so it only runs against the in-process app")

    from plym.main import app

    site = app.state.site
    previous = site.pagination.page_size
    site.pagination.page_size = 1
    try:
        await published_posts(2)
        base = site.public_blog_url()

        first = await client.get("/")
        assert f'<link rel="canonical" href="{base}/">' in first.text
        assert f'<link rel="next" href="{site.blog_prefix}/page/2">' in first.text

        second = await client.get("/page/2")
        assert f'<link rel="canonical" href="{base}/page/2">' in second.text
        assert f'<link rel="prev" href="{site.blog_prefix}/">' in second.text
    finally:
        site.pagination.page_size = previous


@pytest.mark.asyncio
async def test_canonical_redirects_have_a_bounded_lifetime(client: httpx.AsyncClient) -> None:
    from plym.render.cache_policy import REDIRECT_CACHE_CONTROL

    redirect = await client.get("/", params={"page": 2}, follow_redirects=False)
    assert redirect.status_code == 308
    assert redirect.headers["cache-control"] == REDIRECT_CACHE_CONTROL

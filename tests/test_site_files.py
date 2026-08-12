import httpx
import pytest

from plym.service.site_files_service import LLMS_FILE, ROBOTS_FILE, SITEMAP_FILE
from tests.conftest import TEST_MODE

SITE_FILES = (SITEMAP_FILE, LLMS_FILE, ROBOTS_FILE, "index.json")


def _artifact(name: str) -> str:
    if TEST_MODE != "inprocess":
        pytest.skip("reads .generated/ directly, so it needs the in-process app")
    from plym.settings import settings

    target = settings.generated_dir / name
    return target.read_text(encoding="utf-8") if target.exists() else ""


async def _publish(client: httpx.AsyncClient, headers: dict[str, str], slug: str) -> int:
    created = await client.post(
        "/api/posts",
        json={"title": f"Site file {slug}", "slug": slug, "content": "body"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    post_id: int = created.json()["id"]
    published = await client.patch(
        f"/api/posts/{post_id}", json={"status": "published"}, headers=headers
    )
    assert published.status_code == 200, published.text
    return post_id


@pytest.mark.asyncio
async def test_publishing_writes_the_site_files_to_disk(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    post_id = await _publish(client, auth_headers, unique_slug)
    try:
        assert unique_slug in _artifact(SITEMAP_FILE)
        assert unique_slug in _artifact(LLMS_FILE)
        assert "User-agent: *" in _artifact(ROBOTS_FILE)
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_unpublishing_and_deleting_refresh_the_site_files(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    post_id = await _publish(client, auth_headers, unique_slug)
    try:
        assert unique_slug in _artifact(SITEMAP_FILE)

        await client.patch(f"/api/posts/{post_id}", json={"status": "draft"}, headers=auth_headers)
        assert unique_slug not in _artifact(SITEMAP_FILE)
        assert unique_slug not in _artifact(LLMS_FILE)

        await client.patch(
            f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
        )
        assert unique_slug in _artifact(SITEMAP_FILE)
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)

    assert unique_slug not in _artifact(SITEMAP_FILE)
    assert unique_slug not in _artifact(LLMS_FILE)


@pytest.mark.asyncio
async def test_the_artifact_and_the_route_agree_byte_for_byte(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    post_id = await _publish(client, auth_headers, unique_slug)
    try:
        for name in (SITEMAP_FILE, LLMS_FILE, ROBOTS_FILE):
            served = await client.get(f"/{name}")
            assert served.status_code == 200, name
            assert served.text == _artifact(name), name
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_every_site_file_carries_the_listing_policy(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    post_id = await _publish(client, auth_headers, unique_slug)
    try:
        await client.post("/api/index", headers=auth_headers)
        for name in SITE_FILES:
            served = await client.get(f"/{name}")
            assert served.status_code == 200, name
            assert served.headers["cache-control"] == "public, max-age=60", name
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_robots_is_not_written_when_it_is_not_served(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    if TEST_MODE != "inprocess":
        pytest.skip("moves the running site config, so it only runs against the in-process app")

    from plym.main import app
    from plym.settings import settings

    site = app.state.site
    previous = site.robots.serve
    post_id = await _publish(client, auth_headers, unique_slug)
    try:
        site.robots.serve = False
        await client.patch(f"/api/posts/{post_id}", json={"title": "Moved"}, headers=auth_headers)
        assert not (settings.generated_dir / ROBOTS_FILE).exists()
        assert (await client.get(f"/{ROBOTS_FILE}")).status_code == 404
    finally:
        site.robots.serve = previous
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)

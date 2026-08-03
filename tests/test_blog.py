import os
import subprocess
import sys
import textwrap
from pathlib import Path

import httpx
import pytest

from tests.conftest import BASE_URL, TEST_MODE


@pytest.mark.asyncio
async def test_index_returns_html(client: httpx.AsyncClient) -> None:
    r = await client.get("/")
    assert r.status_code == 200
    assert "<html" in r.text.lower()
    assert "cache-control" in {k.lower() for k in r.headers}


# The default layout hosts the blog at the root, where `/` is the index itself;
# the redirect from `/` to the blog home only exists on prefixed layouts, so it
# is probed in a child process against its own /blog config.
_PREFIXED_REDIRECT_PROBE = textwrap.dedent(
    """
    import asyncio, sys

    import httpx

    from plym.config.site import load_site_config
    from plym.main import app

    app.state.site = load_site_config()
    app.state.css = ""
    app.state.prism_js = ""


    async def main() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://probe") as c:
            root = await c.get("/", follow_redirects=False)
            bare = await c.get("/blog", follow_redirects=False)
        print(root.status_code, root.headers.get("location"))
        print(bare.status_code, bare.headers.get("location"))
        ok = (
            root.status_code == 308
            and root.headers.get("location") == "/blog/"
            and bare.status_code == 308
            and bare.headers.get("location") == "/blog/"
        )
        sys.exit(0 if ok else 1)


    asyncio.run(main())
    """
)


def test_root_redirects_to_a_prefixed_blog_home(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    for name in ("_uploads", ".generated", "backups", "webfonts", "static"):
        (storage / name).mkdir(parents=True)
    config = tmp_path / "config.yaml"
    config.write_text(
        'blog_prefix: "/blog"\nwebsite: plym.local\nblog_home: plym.local/blog\n',
        encoding="utf-8",
    )

    probe = subprocess.run(
        [sys.executable, "-c", _PREFIXED_REDIRECT_PROBE],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PLYM_CONFIG_PATH": str(config),
            "PLYM_STORAGE_DIR": str(storage),
            "PLYM_UPLOADS_DIR": str(storage / "_uploads"),
            "PLYM_GENERATED_DIR": str(storage / ".generated"),
            "PLYM_BACKUPS_DIR": str(storage / "backups"),
            "PLYM_FONTS_DIR": str(storage / "webfonts"),
            "PLYM_STATIC_DIR": str(storage / "static"),
            "PLYM_JWT_SECRET": "probe-secret-0123456789abcdef",
            "PLYM_SUPERUSER_EMAIL": "root@plym.local",
            "PLYM_SUPERUSER_PASSWORD": "probe-password",
            "PLYM_TRACE_EXPORTER": "none",
        },
    )
    assert probe.returncode == 0, probe.stdout + probe.stderr


@pytest.mark.asyncio
async def test_trailing_slash_redirect_is_permanent_and_relative(
    client: httpx.AsyncClient,
) -> None:
    r = await client.get("/some-post/", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"] == "/some-post"


@pytest.mark.asyncio
async def test_redirect_location_never_echoes_the_host(client: httpx.AsyncClient) -> None:
    r = await client.get(
        "/some-post/",
        headers={"Host": "origin-7.internal.example.com"},
        follow_redirects=False,
    )
    assert r.status_code == 308
    assert r.headers["location"] == "/some-post"


@pytest.mark.asyncio
async def test_blog_missing_slug_404(client: httpx.AsyncClient) -> None:
    r = await client.get("/this-slug-does-not-exist-anywhere")
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

        r = await client.get(f"/{unique_slug}")
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
        r = await c.get("/")
        assert r.status_code == 200
        assert r.headers.get("content-encoding") == "gzip"
        assert "accept-encoding" in r.headers.get("vary", "").lower()


@pytest.mark.asyncio
async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

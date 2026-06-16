from collections.abc import Awaitable, Callable

import httpx
import pytest


@pytest.mark.asyncio
async def test_upload_returns_metadata(
    client: httpx.AsyncClient, auth_headers: dict[str, str], png_bytes: bytes
) -> None:
    files = {"file": ("test.png", png_bytes, "image/png")}
    r = await client.post("/api/media", files=files, headers=auth_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    media_id = body["id"]

    try:
        assert body["mime_type"] == "image/webp"
        assert body["width"] == 32
        assert body["height"] == 32
        assert body["size_bytes"] > 0
        assert body["url"].endswith(".webp")
        assert body["original_name"] == "test.png"
    finally:
        await client.delete(f"/api/media/{media_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_delete_blocked_when_referenced_in_post(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    png_bytes: bytes,
    unique_slug: str,
) -> None:
    files = {"file": ("ref.png", png_bytes, "image/png")}
    r = await client.post("/api/media", files=files, headers=auth_headers)
    media = r.json()
    media_id = media["id"]
    url = media["url"]

    r = await client.post(
        "/api/posts",
        json={"title": "Refs", "slug": unique_slug, "content": "x", "cover": url},
        headers=auth_headers,
    )
    post_id = r.json()["id"]

    try:
        r = await client.delete(f"/api/media/{media_id}", headers=auth_headers)
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["code"] == "media.in_use"
        assert any(ref["id"] == post_id for ref in detail["referenced_by"])

        await client.patch(
            f"/api/posts/{post_id}", json={"cover": None}, headers=auth_headers
        )
        r = await client.delete(f"/api/media/{media_id}", headers=auth_headers)
        assert r.status_code == 204
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_upload_rejects_non_image(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    files = {"file": ("note.txt", b"not an image", "text/plain")}
    r = await client.post("/api/media", files=files, headers=auth_headers)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "media.unsupported_image"


@pytest.mark.asyncio
async def test_media_list_returns_uploads(
    client: httpx.AsyncClient, auth_headers: dict[str, str], png_bytes: bytes
) -> None:
    files = {"file": ("listed.png", png_bytes, "image/png")}
    r = await client.post("/api/media", files=files, headers=auth_headers)
    media_id = r.json()["id"]
    try:
        r = await client.get("/api/media", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert any(item["id"] == media_id for item in body["items"])
    finally:
        await client.delete(f"/api/media/{media_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_get_media_by_id(
    client: httpx.AsyncClient, auth_headers: dict[str, str], png_bytes: bytes
) -> None:
    files = {"file": ("single.png", png_bytes, "image/png")}
    r = await client.post("/api/media", files=files, headers=auth_headers)
    media_id = r.json()["id"]
    try:
        got = await client.get(f"/api/media/{media_id}", headers=auth_headers)
        assert got.status_code == 200
        assert got.json()["id"] == media_id
    finally:
        await client.delete(f"/api/media/{media_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_get_missing_media_returns_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.get("/api/media/999999999", headers=auth_headers)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "media.not_found"


@pytest.mark.asyncio
async def test_delete_media_forbidden_for_non_uploader(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    png_bytes: bytes,
    user_factory: Callable[..., Awaitable[dict]],
) -> None:
    files = {"file": ("owned.png", png_bytes, "image/png")}
    upload = await client.post("/api/media", files=files, headers=auth_headers)
    media_id = upload.json()["id"]
    try:
        other_editor = await user_factory(role="editor")
        r = await client.delete(f"/api/media/{media_id}", headers=other_editor["headers"])
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "media.forbidden"
    finally:
        await client.delete(f"/api/media/{media_id}", headers=auth_headers)

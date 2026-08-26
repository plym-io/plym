import json
import os
from typing import Any

import httpx
import pytest

TEST_MODE = os.environ.get("PLYM_TEST_MODE", "live")


async def _publish_post(
    client: httpx.AsyncClient, auth_headers: dict[str, str], slug: str, **fields: Any
) -> int:
    payload = {
        "title": fields.get("title", "Search fixture"),
        "slug": slug,
        "content": fields.get("content", "body"),
        "excerpt": fields.get("excerpt"),
        "tags": fields.get("tags", []),
    }
    r = await client.post("/api/posts", json=payload, headers=auth_headers)
    assert r.status_code == 201, r.text
    post_id: int = r.json()["id"]
    r = await client.patch(
        f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    return post_id


async def test_build_and_serve_index_json(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    content = "# Heading\n\nSome **bold** prose about `flux capacitors`."
    post_id = await _publish_post(
        client,
        auth_headers,
        unique_slug,
        title="Flux capacitor guide",
        content=content,
        excerpt="A short excerpt",
        tags=["physics"],
    )
    try:
        r = await client.post("/api/index", headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json()["documents"] >= 1

        r = await client.get("/index.json")
        assert r.status_code == 200
        assert "application/json" in r.headers["content-type"]
        index = r.json()
        assert index["version"] == 2
        assert index["count"] == len(index["documents"])

        doc = next(d for d in index["documents"] if d["slug"] == unique_slug)
        assert doc["title"] == "Flux capacitor guide"
        assert doc["excerpt"] == "A short excerpt"
        assert doc["tags"] == ["physics"]
        assert doc["url"].endswith(f"/{unique_slug}")
        assert "text" not in doc
        assert "flux capacitors" not in r.text
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


async def test_index_carries_no_post_body(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    marker = "sarsaparilla-tachyon"
    post_id = await _publish_post(
        client,
        auth_headers,
        unique_slug,
        content=f"# Heading\n\nProse mentioning {marker} once.",
        excerpt="A short excerpt",
    )
    try:
        r = await client.post("/api/index", headers=auth_headers)
        assert r.status_code == 200, r.text

        r = await client.get("/index.json")
        assert r.status_code == 200
        assert marker not in r.text

        doc = next(d for d in r.json()["documents"] if d["slug"] == unique_slug)
        assert set(doc) == {
            "id",
            "slug",
            "url",
            "title",
            "excerpt",
            "category",
            "tags",
            "author",
            "reading_time",
            "published_at",
            "updated_at",
        }
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


async def test_index_excludes_drafts(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={"title": "Draft fixture", "slug": unique_slug, "content": "draft body"},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    post_id = r.json()["id"]
    try:
        r = await client.post("/api/index", headers=auth_headers)
        assert r.status_code == 200, r.text

        r = await client.get("/index.json")
        assert r.status_code == 200
        slugs = [d["slug"] for d in r.json()["documents"]]
        assert unique_slug not in slugs
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


async def test_build_requires_editor(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/index")
    assert r.status_code == 401


@pytest.mark.skipif(TEST_MODE != "inprocess", reason="needs direct filesystem access")
async def test_index_json_404_when_not_built(client: httpx.AsyncClient) -> None:
    from plym.service.search_index_service import index_path

    index_path().unlink(missing_ok=True)
    r = await client.get("/index.json")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "search.index_not_built"


@pytest.mark.skipif(TEST_MODE != "inprocess", reason="needs direct filesystem access")
async def test_rebuilding_an_unchanged_index_leaves_the_artifact_alone(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    from plym.service.search_index_service import index_path

    post_id = await _publish_post(client, auth_headers, unique_slug)
    try:
        r = await client.post("/api/index", headers=auth_headers)
        assert r.status_code == 200, r.text
        generated_at = r.json()["generated_at"]
        target = index_path()
        body = target.read_bytes()
        touched_at = target.stat().st_mtime_ns

        r = await client.post("/api/index", headers=auth_headers)
        assert r.status_code == 200, r.text

        assert target.read_bytes() == body
        assert target.stat().st_mtime_ns == touched_at
        assert r.json()["generated_at"] == generated_at
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.skipif(TEST_MODE != "inprocess", reason="needs direct filesystem access")
async def test_rebuilding_a_changed_index_rewrites_the_artifact(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    from plym.service.search_index_service import index_path

    post_id = await _publish_post(client, auth_headers, unique_slug, title="Before")
    try:
        assert (await client.post("/api/index", headers=auth_headers)).status_code == 200
        target = index_path()
        body = target.read_bytes()

        r = await client.patch(
            f"/api/posts/{post_id}", json={"title": "After"}, headers=auth_headers
        )
        assert r.status_code == 200, r.text
        assert (await client.post("/api/index", headers=auth_headers)).status_code == 200

        assert target.read_bytes() != body
        doc = next(
            d
            for d in json.loads(target.read_text(encoding="utf-8"))["documents"]
            if d["slug"] == unique_slug
        )
        assert doc["title"] == "After"
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)

import os

import httpx
import pytest

TEST_MODE = os.environ.get("PLYM_TEST_MODE", "live")


async def _publish_post(
    client: httpx.AsyncClient, auth_headers: dict[str, str], slug: str, **fields
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
    post_id = r.json()["id"]
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
        assert index["version"] == 1
        assert index["count"] == len(index["documents"])

        doc = next(d for d in index["documents"] if d["slug"] == unique_slug)
        assert doc["title"] == "Flux capacitor guide"
        assert doc["excerpt"] == "A short excerpt"
        assert doc["tags"] == ["physics"]
        assert doc["url"].endswith(f"/{unique_slug}")
        assert "Some bold prose about flux capacitors." in doc["text"]
        assert "**" not in doc["text"]
        assert "#" not in doc["text"]
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

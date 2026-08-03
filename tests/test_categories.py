import uuid
from collections.abc import Awaitable, Callable
from typing import Any, cast

import httpx
import pytest


def _name() -> str:
    return f"QA {uuid.uuid4().hex[:10]}"


async def _create_category(
    client: httpx.AsyncClient, headers: dict[str, str], name: str, weight: int | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": name}
    if weight is not None:
        payload["weight"] = weight
    r = await client.post("/api/categories", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return cast(dict[str, Any], r.json())


@pytest.mark.asyncio
async def test_list_categories_is_public_and_shaped(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/categories")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    for item in body:
        assert {"id", "name", "slug", "weight"} <= set(item.keys())


@pytest.mark.asyncio
async def test_create_derives_slug_and_reads_back(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    name = _name()
    created = await _create_category(client, auth_headers, name)
    try:
        assert created["slug"] == name.lower().replace(" ", "-")
        assert created["weight"] is None

        r = await client.get(f"/api/categories/{created['id']}")
        assert r.status_code == 200
        assert r.json() == created
    finally:
        await client.delete(f"/api/categories/{created['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_write_endpoints_require_editor(
    client: httpx.AsyncClient, user_factory: Callable[..., Awaitable[dict[str, Any]]]
) -> None:
    reader = await user_factory(role="reader")
    r = await client.post("/api/categories", json={"name": _name()}, headers=reader["headers"])
    assert r.status_code == 403

    r = await client.post("/api/categories", json={"name": _name()})
    assert r.status_code == 401

    r = await client.patch("/api/categories/1", json={"weight": 1}, headers=reader["headers"])
    assert r.status_code == 403

    r = await client.delete("/api/categories/1", headers=reader["headers"])
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_name_returns_409(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    name = _name()
    created = await _create_category(client, auth_headers, name)
    try:
        r = await client.post("/api/categories", json={"name": name}, headers=auth_headers)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "categories.conflict"
    finally:
        await client.delete(f"/api/categories/{created['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_reserved_and_unsluggable_names_rejected(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    for name in ("static", "Plym Admin", "Plym Docs", "mcp", "page"):
        r = await client.post("/api/categories", json={"name": name}, headers=auth_headers)
        assert r.status_code == 400, name
        assert r.json()["detail"]["code"] == "categories.reserved_name"

    r = await client.post("/api/categories", json={"name": "!!!"}, headers=auth_headers)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "categories.invalid_name"


@pytest.mark.asyncio
async def test_docs_is_not_reserved(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await _create_category(client, auth_headers, "Docs")
    try:
        assert created["slug"] == "docs"
    finally:
        await client.delete(f"/api/categories/{created['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_reserved_post_slugs_rejected(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={"title": "x", "slug": "plym-docs", "content": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "posts.reserved_slug"

    created = await client.post(
        "/api/posts",
        json={"title": "x", "slug": unique_slug, "content": "x"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    try:
        r = await client.patch(f"/api/posts/{post_id}", json={"slug": "page"}, headers=auth_headers)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "posts.reserved_slug"
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_post_slug_may_not_shadow_a_category(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    category = await _create_category(client, auth_headers, _name())
    try:
        r = await client.post(
            "/api/posts",
            json={"title": "shadow", "slug": category["slug"], "content": "x"},
            headers=auth_headers,
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "posts.slug_conflict"
    finally:
        await client.delete(f"/api/categories/{category['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_category_may_not_shadow_a_post_slug(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    created = await client.post(
        "/api/posts",
        json={"title": "holder", "slug": unique_slug, "content": "x"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    other = await _create_category(client, auth_headers, _name())
    try:
        r = await client.post(
            "/api/categories",
            json={"name": unique_slug.replace("-", " ")},
            headers=auth_headers,
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "categories.conflict"

        r = await client.patch(
            f"/api/categories/{other['id']}",
            json={"name": unique_slug.replace("-", " ")},
            headers=auth_headers,
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "categories.conflict"
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)
        await client.delete(f"/api/categories/{other['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_unknown_id_returns_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    assert (await client.get("/api/categories/99999999")).status_code == 404

    r = await client.patch("/api/categories/99999999", json={"weight": 1}, headers=auth_headers)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "categories.not_found"

    r = await client.delete("/api/categories/99999999", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_weight_orders_listing_and_clears(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    base = uuid.uuid4().hex[:10]
    alpha_first, alpha_last = f"aa{base}", f"zz{base}"
    first = await _create_category(client, auth_headers, alpha_first, weight=2)
    last = await _create_category(client, auth_headers, alpha_last, weight=1)
    try:
        listing = (await client.get("/api/categories")).json()
        positions = {c["name"]: idx for idx, c in enumerate(listing)}
        assert positions[alpha_last] < positions[alpha_first]

        r = await client.patch(
            f"/api/categories/{last['id']}", json={"weight": None}, headers=auth_headers
        )
        assert r.status_code == 200
        assert r.json()["weight"] is None

        listing = (await client.get("/api/categories")).json()
        positions = {c["name"]: idx for idx, c in enumerate(listing)}
        assert positions[alpha_first] < positions[alpha_last]
    finally:
        await client.delete(f"/api/categories/{first['id']}", headers=auth_headers)
        await client.delete(f"/api/categories/{last['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_rename_keeps_weight_and_updates_slug(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await _create_category(client, auth_headers, _name(), weight=3)
    try:
        renamed = f"{_name()} Renamed"
        r = await client.patch(
            f"/api/categories/{created['id']}", json={"name": renamed}, headers=auth_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == renamed
        assert body["slug"] == renamed.lower().replace(" ", "-")
        assert body["weight"] == 3
    finally:
        await client.delete(f"/api/categories/{created['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_post_with_category_serves_nested_url(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    category = await _create_category(client, auth_headers, _name())
    created = await client.post(
        "/api/posts",
        json={
            "title": "categorised",
            "slug": unique_slug,
            "content": "# body",
            "category_id": category["id"],
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    post = created.json()
    post_id = post["id"]
    try:
        assert post["category"]["id"] == category["id"]
        assert post["path"] == f"{category['slug']}/{unique_slug}"

        await client.patch(
            f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
        )
        await client.post(f"/api/posts/{post_id}/refresh", headers=auth_headers)

        nested = await client.get(f"/{category['slug']}/{unique_slug}")
        assert nested.status_code == 200
        assert f"/{category['slug']}/{unique_slug}" in nested.text

        assert (await client.get(f"/{unique_slug}")).status_code == 404
        assert (await client.get(f"/other-category/{unique_slug}")).status_code == 404
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)
        await client.delete(f"/api/categories/{category['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_unknown_category_on_post_returns_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={"title": "x", "slug": unique_slug, "content": "x", "category_id": 99999999},
        headers=auth_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "categories.not_found"

    created = await client.post(
        "/api/posts",
        json={"title": "x", "slug": unique_slug, "content": "x"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    try:
        r = await client.patch(
            f"/api/posts/{post_id}", json={"category_id": 99999999}, headers=auth_headers
        )
        assert r.status_code == 404
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_delete_category_in_use_returns_409(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    category = await _create_category(client, auth_headers, _name())
    created = await client.post(
        "/api/posts",
        json={
            "title": "held",
            "slug": unique_slug,
            "content": "x",
            "category_id": category["id"],
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    try:
        r = await client.delete(f"/api/categories/{category['id']}", headers=auth_headers)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "categories.in_use"

        r = await client.patch(
            f"/api/posts/{post_id}", json={"category_id": None}, headers=auth_headers
        )
        assert r.status_code == 200
        assert r.json()["category"] is None
        assert r.json()["path"] == unique_slug

        assert (
            await client.delete(f"/api/categories/{category['id']}", headers=auth_headers)
        ).status_code == 204
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_category_rename_moves_served_url(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    category = await _create_category(client, auth_headers, _name())
    created = await client.post(
        "/api/posts",
        json={
            "title": "renamed home",
            "slug": unique_slug,
            "content": "# body",
            "category_id": category["id"],
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    try:
        await client.patch(
            f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
        )
        await client.post(f"/api/posts/{post_id}/refresh", headers=auth_headers)
        assert (await client.get(f"/{category['slug']}/{unique_slug}")).status_code == 200

        renamed = f"{_name()} Moved"
        r = await client.patch(
            f"/api/categories/{category['id']}", json={"name": renamed}, headers=auth_headers
        )
        assert r.status_code == 200
        new_slug = r.json()["slug"]

        assert (await client.get(f"/{new_slug}/{unique_slug}")).status_code == 200
        assert (await client.get(f"/{category['slug']}/{unique_slug}")).status_code == 404
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)
        await client.delete(f"/api/categories/{category['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_moving_post_between_categories_moves_url(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    source = await _create_category(client, auth_headers, _name())
    destination = await _create_category(client, auth_headers, _name())
    created = await client.post(
        "/api/posts",
        json={
            "title": "mover",
            "slug": unique_slug,
            "content": "# body",
            "category_id": source["id"],
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    try:
        await client.patch(
            f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
        )
        await client.post(f"/api/posts/{post_id}/refresh", headers=auth_headers)
        assert (await client.get(f"/{source['slug']}/{unique_slug}")).status_code == 200

        r = await client.patch(
            f"/api/posts/{post_id}",
            json={"category_id": destination["id"]},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["path"] == f"{destination['slug']}/{unique_slug}"

        assert (await client.get(f"/{destination['slug']}/{unique_slug}")).status_code == 200
        assert (await client.get(f"/{source['slug']}/{unique_slug}")).status_code == 404
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)
        await client.delete(f"/api/categories/{source['id']}", headers=auth_headers)
        await client.delete(f"/api/categories/{destination['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_category_path_in_sitemap_llms_and_search_index(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    category = await _create_category(client, auth_headers, _name())
    created = await client.post(
        "/api/posts",
        json={
            "title": "indexed",
            "slug": unique_slug,
            "content": "# body",
            "excerpt": "why it matters",
            "category_id": category["id"],
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    expected = f"{category['slug']}/{unique_slug}"
    try:
        await client.patch(
            f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
        )

        sitemap = await client.get("/sitemap.xml")
        assert sitemap.status_code == 200
        assert f"/{expected}</loc>" in sitemap.text

        llms = await client.get("/llms.txt")
        assert llms.status_code == 200
        assert f"/{expected})" in llms.text

        built = await client.post("/api/index", headers=auth_headers)
        assert built.status_code == 200
        index = (await client.get("/index.json")).json()
        doc = next(d for d in index["documents"] if d["slug"] == unique_slug)
        assert doc["url"].endswith(f"/{expected}")
        assert doc["category"] == category["slug"]
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)
        await client.delete(f"/api/categories/{category['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_search_index_follows_category_changes(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    source = await _create_category(client, auth_headers, _name())
    destination = await _create_category(client, auth_headers, _name())
    created = await client.post(
        "/api/posts",
        json={
            "title": "tracked",
            "slug": unique_slug,
            "content": "# body",
            "category_id": source["id"],
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    post_id = created.json()["id"]

    def doc_for(index: dict[str, Any]) -> dict[str, Any]:
        return next(d for d in index["documents"] if d["slug"] == unique_slug)

    try:
        await client.patch(
            f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
        )
        await client.post(f"/api/posts/{post_id}/refresh", headers=auth_headers)
        assert (await client.post("/api/index", headers=auth_headers)).status_code == 200

        r = await client.patch(
            f"/api/posts/{post_id}",
            json={"category_id": destination["id"]},
            headers=auth_headers,
        )
        assert r.status_code == 200
        index = (await client.get("/index.json")).json()
        assert doc_for(index)["url"].endswith(f"/{destination['slug']}/{unique_slug}")

        renamed = f"{_name()} Tracked"
        r = await client.patch(
            f"/api/categories/{destination['id']}", json={"name": renamed}, headers=auth_headers
        )
        assert r.status_code == 200
        new_slug = r.json()["slug"]
        index = (await client.get("/index.json")).json()
        assert doc_for(index)["url"].endswith(f"/{new_slug}/{unique_slug}")
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)
        await client.delete(f"/api/categories/{source['id']}", headers=auth_headers)
        await client.delete(f"/api/categories/{destination['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_post_and_category_cannot_claim_the_same_segment(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    created = await client.post(
        "/api/posts",
        json={"title": "Claimed", "slug": unique_slug, "content": "x"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    post_id = created.json()["id"]
    try:
        clash = await client.post(
            "/api/categories", json={"name": unique_slug.replace("-", " ")}, headers=auth_headers
        )
        assert clash.status_code == 409
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)

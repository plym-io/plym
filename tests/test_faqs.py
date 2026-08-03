import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest


def _faq_payload() -> dict[str, Any]:
    marker = uuid.uuid4().hex[:10]
    return {"question": f"What is {marker}?", "answer": f"It is {marker}."}


@pytest.mark.asyncio
async def test_faq_crud_lifecycle(client: httpx.AsyncClient, auth_headers: dict[str, str]) -> None:
    payload = _faq_payload()
    created = await client.post("/api/faqs", json=payload, headers=auth_headers)
    assert created.status_code == 201, created.text
    faq = created.json()
    assert {"id", "question", "answer"} == set(faq.keys())
    assert faq["question"] == payload["question"]
    faq_id = faq["id"]
    try:
        fetched = await client.get(f"/api/faqs/{faq_id}")
        assert fetched.status_code == 200
        assert fetched.json() == faq

        listing = await client.get("/api/faqs")
        assert listing.status_code == 200
        assert any(f["id"] == faq_id for f in listing.json())

        updated = await client.put(
            f"/api/faqs/{faq_id}",
            json={"question": payload["question"], "answer": "Revised answer."},
            headers=auth_headers,
        )
        assert updated.status_code == 200
        assert updated.json()["answer"] == "Revised answer."
    finally:
        deleted = await client.delete(f"/api/faqs/{faq_id}", headers=auth_headers)
        assert deleted.status_code == 204

    gone = await client.get(f"/api/faqs/{faq_id}")
    assert gone.status_code == 404
    assert gone.json()["detail"]["code"] == "faqs.not_found"


@pytest.mark.asyncio
async def test_faq_writes_require_editor(
    client: httpx.AsyncClient, user_factory: Callable[..., Awaitable[dict[str, Any]]]
) -> None:
    reader = await user_factory(role="reader")
    payload = _faq_payload()

    forbidden = await client.post("/api/faqs", json=payload, headers=reader["headers"])
    assert forbidden.status_code == 403

    unauthorized = await client.post("/api/faqs", json=payload)
    assert unauthorized.status_code == 401


@pytest.mark.asyncio
async def test_faq_get_unknown_returns_404(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/faqs/99999999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "faqs.not_found"


@pytest.mark.asyncio
async def test_post_renders_selected_faqs_in_order(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    first = (await client.post("/api/faqs", json=_faq_payload(), headers=auth_headers)).json()
    second = (await client.post("/api/faqs", json=_faq_payload(), headers=auth_headers)).json()
    created = await client.post(
        "/api/posts",
        json={
            "title": "faqed",
            "slug": unique_slug,
            "content": "x",
            "faqs": [second["id"], first["id"]],
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    post_id = created.json()["id"]
    try:
        post = (await client.get(f"/api/posts/{post_id}", headers=auth_headers)).json()
        ids = [f["id"] for f in post["faqs"]]
        assert ids == [second["id"], first["id"]]
        assert post["faqs"][0]["question"] == second["question"]
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)
        await client.delete(f"/api/faqs/{first['id']}", headers=auth_headers)
        await client.delete(f"/api/faqs/{second['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_post_with_unknown_faq_id_returns_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    r = await client.post(
        "/api/posts",
        json={"title": "bad", "slug": unique_slug, "content": "x", "faqs": [99999999]},
        headers=auth_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "faqs.not_found"

    listing = await client.get("/api/posts", headers=auth_headers)
    assert all(p["slug"] != unique_slug for p in listing.json()["items"])


@pytest.mark.asyncio
async def test_faq_jsonld_in_rendered_post(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    faq = (await client.post("/api/faqs", json=_faq_payload(), headers=auth_headers)).json()
    created = await client.post(
        "/api/posts",
        json={
            "title": "published-faq",
            "slug": unique_slug,
            "content": "hello",
            "faqs": [faq["id"]],
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    post_id = created.json()["id"]
    try:
        published = await client.patch(
            f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
        )
        assert published.status_code == 200
        refreshed = await client.post(f"/api/posts/{post_id}/refresh", headers=auth_headers)
        assert refreshed.status_code == 200

        served = await client.get(f"/{unique_slug}")
        assert served.status_code == 200, served.text
        html = served.text
        assert "application/ld+json" in html
        assert '"@type": "FAQPage"' in html
        assert faq["question"] in html
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)
        await client.delete(f"/api/faqs/{faq['id']}", headers=auth_headers)


async def _publish_post_with_faq(
    client: httpx.AsyncClient, auth_headers: dict[str, str], slug: str, faq_id: int
) -> int:
    created = await client.post(
        "/api/posts",
        json={"title": "faq sweep", "slug": slug, "content": "hello", "faqs": [faq_id]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    post_id = int(created.json()["id"])
    published = await client.patch(
        f"/api/posts/{post_id}", json={"status": "published"}, headers=auth_headers
    )
    assert published.status_code == 200, published.text
    return post_id


@pytest.mark.asyncio
async def test_faq_update_rerenders_published_post(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    faq = (await client.post("/api/faqs", json=_faq_payload(), headers=auth_headers)).json()
    post_id = await _publish_post_with_faq(client, auth_headers, unique_slug, faq["id"])
    try:
        assert faq["answer"] in (await client.get(f"/{unique_slug}")).text

        revised = f"Revised answer {uuid.uuid4().hex[:8]}."
        updated = await client.put(
            f"/api/faqs/{faq['id']}",
            json={"question": faq["question"], "answer": revised},
            headers=auth_headers,
        )
        assert updated.status_code == 200, updated.text

        served = await client.get(f"/{unique_slug}")
        assert served.status_code == 200, served.text
        assert revised in served.text
        assert faq["answer"] not in served.text
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)
        await client.delete(f"/api/faqs/{faq['id']}", headers=auth_headers)


@pytest.mark.asyncio
async def test_faq_delete_rerenders_published_post(
    client: httpx.AsyncClient, auth_headers: dict[str, str], unique_slug: str
) -> None:
    faq = (await client.post("/api/faqs", json=_faq_payload(), headers=auth_headers)).json()
    post_id = await _publish_post_with_faq(client, auth_headers, unique_slug, faq["id"])
    try:
        assert faq["question"] in (await client.get(f"/{unique_slug}")).text

        deleted = await client.delete(f"/api/faqs/{faq['id']}", headers=auth_headers)
        assert deleted.status_code == 204

        served = await client.get(f"/{unique_slug}")
        assert served.status_code == 200, served.text
        assert faq["question"] not in served.text
        assert '"@type": "FAQPage"' not in served.text
    finally:
        await client.delete(f"/api/posts/{post_id}", headers=auth_headers)

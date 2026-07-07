from collections.abc import Awaitable, Callable

import httpx
import pytest


@pytest.mark.asyncio
async def test_collect_is_public_and_returns_receipt(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/collect", json={"email": "lead@example.com", "source": "hero"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert isinstance(body["id"], int)
    assert body["created_at"]
    assert set(body) == {"id", "created_at"}


@pytest.mark.asyncio
async def test_collect_stores_payload_ua_and_forwarded_ip(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {"email": "lead@example.com", "source": "pricing", "nested": {"utm": "x"}}
    r = await client.post(
        "/api/collect",
        json=payload,
        headers={"User-Agent": "acme-bot/1.0", "X-Forwarded-For": "203.0.113.7, 10.0.0.1"},
    )
    submission_id = r.json()["id"]

    listing = await client.get("/api/submissions", headers=auth_headers)
    assert listing.status_code == 200, listing.text
    row = next(item for item in listing.json()["items"] if item["id"] == submission_id)
    assert row["payload"] == payload
    assert row["user_agent"] == "acme-bot/1.0"
    assert row["client_addr"] == "203.0.113.7"


@pytest.mark.asyncio
async def test_collect_drops_malformed_forwarded_ip(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.post(
        "/api/collect",
        json={"email": "lead@example.com"},
        headers={"X-Forwarded-For": "not-an-ip"},
    )
    submission_id = r.json()["id"]

    listing = await client.get("/api/submissions", headers=auth_headers)
    row = next(item for item in listing.json()["items"] if item["id"] == submission_id)
    assert row["client_addr"] is None


@pytest.mark.asyncio
async def test_list_requires_administrator(
    client: httpx.AsyncClient,
    user_factory: Callable[..., Awaitable[dict]],
) -> None:
    anon = await client.get("/api/submissions")
    assert anon.status_code == 401

    editor = await user_factory(role="editor")
    forbidden = await client.get("/api/submissions", headers=editor["headers"])
    assert forbidden.status_code == 403

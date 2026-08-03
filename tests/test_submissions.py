import ipaddress
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from plym.service.submission_service import FixedWindowRateLimiter, client_ip


def _is_ip(value: str | None) -> bool:
    if value is None:
        return True
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


@pytest.mark.parametrize(
    ("forwarded_for", "peer", "trusted_hops", "expected"),
    [
        ("203.0.113.7", None, 1, "203.0.113.7"),
        ("203.0.113.7, 10.0.0.1, 172.18.0.1", None, 1, "172.18.0.1"),
        ("203.0.113.7, 10.0.0.1, 172.18.0.1", None, 2, "10.0.0.1"),
        ("203.0.113.7, 10.0.0.1, 172.18.0.1", None, 3, "203.0.113.7"),
        ("203.0.113.7, 10.0.0.1, 172.18.0.1", "198.51.100.9", 4, "198.51.100.9"),
        ("203.0.113.7", "198.51.100.9", 0, "198.51.100.9"),
        ("203.0.113.7,,", None, 1, "203.0.113.7"),
        ("  203.0.113.7  ", None, 1, "203.0.113.7"),
        ("2001:db8::1", None, 1, "2001:db8::1"),
        ("not-an-ip", None, 1, None),
        ("not-an-ip", "198.51.100.9", 1, None),
        (None, "198.51.100.9", 1, "198.51.100.9"),
        ("", "198.51.100.9", 1, "198.51.100.9"),
        (None, None, 1, None),
        (None, "garbage", 1, None),
    ],
)
def test_client_ip(
    forwarded_for: str | None, peer: str | None, trusted_hops: int, expected: str | None
) -> None:
    assert client_ip(forwarded_for, peer, trusted_hops) == expected


def test_rate_limiter_admits_up_to_the_limit_then_refuses() -> None:
    limiter = FixedWindowRateLimiter(limit=3, window_seconds=60.0, max_clients=100)
    assert [limiter.hit("203.0.113.7", 0.0) for _ in range(3)] == [0.0, 0.0, 0.0]
    assert limiter.hit("203.0.113.7", 10.0) == pytest.approx(50.0)
    assert limiter.hit("198.51.100.9", 10.0) == 0.0


def test_rate_limiter_window_rolls_over() -> None:
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60.0, max_clients=100)
    assert limiter.hit("203.0.113.7", 0.0) == 0.0
    assert limiter.hit("203.0.113.7", 59.0) == pytest.approx(1.0)
    assert limiter.hit("203.0.113.7", 60.0) == 0.0


def test_rate_limiter_memory_is_bounded_by_max_clients() -> None:
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60.0, max_clients=8)
    for octet in range(200):
        limiter.hit(f"203.0.113.{octet}", 0.0)
    assert len(limiter) == 8
    assert limiter.hit("203.0.113.199", 0.0) == pytest.approx(60.0)
    assert limiter.hit("203.0.113.0", 0.0) == 0.0


@pytest.mark.asyncio
async def test_collect_is_public_and_returns_receipt(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/collect", json={"email": "lead@example.com", "source": "hero"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert isinstance(body["id"], int)
    assert body["created_at"]
    assert set(body) == {"id", "created_at"}


@pytest.mark.asyncio
async def test_collect_stores_payload_and_user_agent(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {"email": "lead@example.com", "source": "pricing", "nested": {"utm": "x"}}
    r = await client.post("/api/collect", json=payload, headers={"User-Agent": "acme-bot/1.0"})
    submission_id = r.json()["id"]

    listing = await client.get("/api/submissions", headers=auth_headers)
    assert listing.status_code == 200, listing.text
    row = next(item for item in listing.json()["items"] if item["id"] == submission_id)
    assert row["payload"] == payload
    assert row["user_agent"] == "acme-bot/1.0"
    assert _is_ip(row["client_addr"])
    assert row["additional_ctx"] is None


@pytest.mark.asyncio
async def test_collect_rejects_oversized_payload(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/collect", json={"blob": "x" * (1024 * 1024)})
    assert r.status_code == 413, r.text
    assert r.json()["detail"]["code"] == "submission.too_large"


@pytest.mark.asyncio
async def test_collect_rejects_non_object_body(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/collect", json=["not", "an", "object"])
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "submission.malformed"


@pytest.mark.asyncio
async def test_collect_ignores_spoofed_leftmost_forwarded_for(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    spoofed = "203.0.113.7"
    r = await client.post(
        "/api/collect",
        json={"email": "lead@example.com"},
        headers={"X-Forwarded-For": f"{spoofed}, 198.51.100.4"},
    )
    submission_id = r.json()["id"]

    listing = await client.get("/api/submissions", headers=auth_headers)
    row = next(item for item in listing.json()["items"] if item["id"] == submission_id)
    assert row["client_addr"] != spoofed
    assert _is_ip(row["client_addr"])


@pytest.mark.asyncio
async def test_list_requires_administrator(
    client: httpx.AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    anon = await client.get("/api/submissions")
    assert anon.status_code == 401

    editor = await user_factory(role="editor")
    forbidden = await client.get("/api/submissions", headers=editor["headers"])
    assert forbidden.status_code == 403

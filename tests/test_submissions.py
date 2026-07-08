import ipaddress
from collections.abc import Awaitable, Callable

import httpx
import pytest

from plym.service.submission_service import _normalise_ip


def _is_ip(value: str | None) -> bool:
    if value is None:
        return True
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


@pytest.mark.parametrize(
    ("forwarded_for", "peer", "expected"),
    [
        ("203.0.113.7", None, "203.0.113.7"),
        ("203.0.113.7, 10.0.0.1, 172.18.0.1", None, "203.0.113.7"),
        ("  203.0.113.7  ", None, "203.0.113.7"),
        ("2001:db8::1", None, "2001:db8::1"),
        ("not-an-ip", None, None),
        ("not-an-ip", "198.51.100.9", None),
        (None, "198.51.100.9", "198.51.100.9"),
        ("", "198.51.100.9", "198.51.100.9"),
        (None, None, None),
        (None, "garbage", None),
    ],
)
def test_normalise_ip(forwarded_for: str | None, peer: str | None, expected: str | None) -> None:
    assert _normalise_ip(forwarded_for, peer) == expected


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
async def test_list_requires_administrator(
    client: httpx.AsyncClient,
    user_factory: Callable[..., Awaitable[dict]],
) -> None:
    anon = await client.get("/api/submissions")
    assert anon.status_code == 401

    editor = await user_factory(role="editor")
    forbidden = await client.get("/api/submissions", headers=editor["headers"])
    assert forbidden.status_code == 403

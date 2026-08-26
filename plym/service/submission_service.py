import ipaddress
import math
from collections import OrderedDict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from plym.exceptions.base import PlymError
from plym.instrumentation.tracer import Traced
from plym.models.submission import Submission, SubmissionPage, SubmissionReceipt
from plym.repository.submission_repository import SubmissionRepository


class SubmissionTooLargeError(PlymError):
    code = "submission.too_large"

    def __init__(self, max_bytes: int) -> None:
        super().__init__(413, f"Submission exceeds {max_bytes} bytes")


class SubmissionMalformedError(PlymError):
    code = "submission.malformed"

    def __init__(self) -> None:
        super().__init__(400, "Submission body must be a JSON object")


class SubmissionRateLimitedError(PlymError):
    code = "submission.rate_limited"

    def __init__(self, retry_after_seconds: float) -> None:
        retry_after = max(1, math.ceil(retry_after_seconds))
        super().__init__(429, f"Too many submissions, retry in {retry_after} seconds")
        self.headers = {"Retry-After": str(retry_after)}


def forwarded_hop(forwarded_for: str | None, trusted_hops: int) -> str | None:
    if trusted_hops < 1 or not forwarded_for:
        return None
    entries = [entry.strip() for entry in forwarded_for.split(",") if entry.strip()]
    if len(entries) < trusted_hops:
        return None
    return entries[-trusted_hops]


def client_ip(forwarded_for: str | None, peer: str | None, trusted_hops: int) -> str | None:
    candidate = forwarded_hop(forwarded_for, trusted_hops) or peer
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate.strip()))
    except ValueError:
        return None


class FixedWindowRateLimiter:
    def __init__(self, *, limit: int, window_seconds: float, max_clients: int) -> None:
        self._limit = limit
        self._window = window_seconds
        self._max_clients = max_clients
        self._windows: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._windows)

    def hit(self, key: str, now: float) -> float:
        self._drop_expired(now)
        window = self._windows.get(key)
        if window is None:
            self._windows[key] = (now, 1)
            self._drop_overflow()
            return 0.0
        started, count = window
        if count >= self._limit:
            return self._window - (now - started)
        self._windows[key] = (started, count + 1)
        return 0.0

    def _drop_expired(self, now: float) -> None:
        while self._windows:
            key, (started, _) = next(iter(self._windows.items()))
            if now - started < self._window:
                return
            del self._windows[key]

    def _drop_overflow(self) -> None:
        while len(self._windows) > self._max_clients:
            self._windows.popitem(last=False)


class SubmissionService(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._submissions = SubmissionRepository(session)

    async def collect(
        self,
        *,
        payload: dict[str, Any],
        user_agent: str | None,
        client_addr: str | None,
    ) -> SubmissionReceipt:
        row = await self._submissions.insert(
            payload=payload,
            user_agent=user_agent,
            client_addr=client_addr,
        )
        await self._session.commit()
        return SubmissionReceipt.model_validate(row)

    async def list_paginated(self, *, page: int, page_size: int) -> SubmissionPage:
        offset = max(0, (page - 1) * page_size)
        rows = await self._submissions.list_paginated(limit=page_size, offset=offset)
        total = int(rows[0]["total"]) if rows else await self._submissions.count()
        return SubmissionPage(
            items=[Submission.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

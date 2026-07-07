import ipaddress
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from plym.instrumentation.tracer import Traced
from plym.models.submission import Submission, SubmissionPage, SubmissionReceipt
from plym.repository.submission_repository import SubmissionRepository


def _normalise_ip(forwarded_for: str | None, peer: str | None) -> str | None:
    candidate = None
    if forwarded_for:
        candidate = forwarded_for.split(",", 1)[0].strip()
    if not candidate:
        candidate = peer
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


class SubmissionService(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._submissions = SubmissionRepository(session)

    async def collect(
        self,
        *,
        payload: dict[str, Any],
        user_agent: str | None,
        forwarded_for: str | None,
        peer: str | None,
    ) -> SubmissionReceipt:
        row = await self._submissions.insert(
            payload=payload,
            user_agent=user_agent,
            client_addr=_normalise_ip(forwarded_for, peer),
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

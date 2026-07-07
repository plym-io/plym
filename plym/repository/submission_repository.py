import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plym.instrumentation.tracer import Traced


class SubmissionRepository(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(
        self,
        *,
        payload: dict[str, Any],
        user_agent: str | None,
        client_addr: str | None,
    ) -> dict:
        result = await self._session.execute(
            text(
                """
                INSERT INTO public.pl_submissions (payload, user_agent, client_addr)
                VALUES (CAST(:payload AS jsonb), :user_agent, CAST(:client_addr AS inet))
                RETURNING id, created_at
                """
            ),
            {
                "payload": json.dumps(payload),
                "user_agent": user_agent,
                "client_addr": client_addr,
            },
        )
        return dict(result.mappings().one())

    async def list_paginated(self, *, limit: int, offset: int) -> list[dict]:
        result = await self._session.execute(
            text(
                """
                SELECT id, payload, user_agent, client_addr, created_at,
                       COUNT(*) OVER() AS total
                FROM public.pl_submissions
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        )
        return [dict(r) for r in result.mappings().all()]

    async def count(self) -> int:
        result = await self._session.execute(text("SELECT COUNT(*) FROM public.pl_submissions"))
        return int(result.scalar_one())

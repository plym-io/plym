import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plym.instrumentation.tracer import Traced


class AuditRepository(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(
        self,
        *,
        event: str,
        actor_id: int | None,
        target: str | None,
        payload: dict[str, Any],
        request_id: str | None,
    ) -> None:
        await self._session.execute(
            text(
                """
                INSERT INTO public.pl_audit (event, actor_id, target, payload, request_id)
                VALUES (:event, :actor_id, :target, CAST(:payload AS JSONB), :request_id)
                """
            ),
            {
                "event": event,
                "actor_id": actor_id,
                "target": target,
                "payload": json.dumps(payload),
                "request_id": request_id,
            },
        )

    def _filters(self, event_prefix: str | None, actor_id: int | None) -> tuple[str, dict]:
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if event_prefix:
            conditions.append("event LIKE :event_prefix")
            params["event_prefix"] = f"{event_prefix}%"
        if actor_id is not None:
            conditions.append("actor_id = :actor_id")
            params["actor_id"] = actor_id
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return where, params

    async def list_paginated(
        self,
        *,
        limit: int,
        offset: int,
        event_prefix: str | None = None,
        actor_id: int | None = None,
    ) -> list[dict]:
        where, params = self._filters(event_prefix, actor_id)
        result = await self._session.execute(
            text(
                f"""
                SELECT id, event, actor_id, target, payload, request_id, created_at
                FROM public.pl_audit
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {**params, "limit": limit, "offset": offset},
        )
        return [dict(r) for r in result.mappings().all()]

    async def count(
        self,
        *,
        event_prefix: str | None = None,
        actor_id: int | None = None,
    ) -> int:
        where, params = self._filters(event_prefix, actor_id)
        result = await self._session.execute(
            text(f"SELECT COUNT(*) FROM public.pl_audit {where}"), params
        )
        return int(result.scalar_one())

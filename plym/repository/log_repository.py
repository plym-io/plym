import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class LogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(
        self,
        *,
        event: str,
        actor_id: int | None,
        target: str | None,
        payload: dict[str, Any],
        audit: bool,
    ) -> None:
        await self._session.execute(
            text(
                """
                INSERT INTO public.pl_logs (event, actor_id, target, payload, audit)
                VALUES (:event, :actor_id, :target, CAST(:payload AS JSONB), :audit)
                """
            ),
            {
                "event": event,
                "actor_id": actor_id,
                "target": target,
                "payload": json.dumps(payload),
                "audit": audit,
            },
        )

    def _filters(
        self, event_prefix: str | None, actor_id: int | None, audit_only: bool
    ) -> tuple[str, dict]:
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if event_prefix:
            conditions.append("event LIKE :event_prefix")
            params["event_prefix"] = f"{event_prefix}%"
        if actor_id is not None:
            conditions.append("actor_id = :actor_id")
            params["actor_id"] = actor_id
        if audit_only:
            conditions.append("audit = TRUE")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return where, params

    async def list_paginated(
        self,
        *,
        limit: int,
        offset: int,
        event_prefix: str | None = None,
        actor_id: int | None = None,
        audit_only: bool = False,
    ) -> list[dict]:
        where, params = self._filters(event_prefix, actor_id, audit_only)
        result = await self._session.execute(
            text(
                f"""
                SELECT id, event, actor_id, target, payload, audit, created_at
                FROM public.pl_logs
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
        audit_only: bool = False,
    ) -> int:
        where, params = self._filters(event_prefix, actor_id, audit_only)
        result = await self._session.execute(
            text(f"SELECT COUNT(*) FROM public.pl_logs {where}"), params
        )
        return int(result.scalar_one())

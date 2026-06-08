from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session, require_admin
from plym.models.log import LogEntry
from plym.repository.log_repository import LogRepository

router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(require_admin)])


class LogPage(BaseModel):
    items: list[LogEntry]
    total: int
    page: int
    page_size: int


@router.get("", response_model=LogPage)
async def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    event_prefix: str | None = Query(None, description="e.g. 'posts' or 'auth.login'"),
    actor_id: int | None = Query(None),
    audit_only: bool = Query(False, description="Only audit-flagged events"),
    session: AsyncSession = Depends(db_session),
) -> LogPage:
    offset = (page - 1) * page_size
    repo = LogRepository(session)
    rows = await repo.list_paginated(
        limit=page_size,
        offset=offset,
        event_prefix=event_prefix,
        actor_id=actor_id,
        audit_only=audit_only,
    )
    total = await repo.count(
        event_prefix=event_prefix, actor_id=actor_id, audit_only=audit_only
    )
    return LogPage(
        items=[LogEntry.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )

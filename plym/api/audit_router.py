from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session, require_admin
from plym.models.audit import AuditEntry
from plym.repository.audit_repository import AuditRepository

router = APIRouter(prefix="/api/audit", tags=["audit"], dependencies=[Depends(require_admin)])


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    page: int
    page_size: int


@router.get("", response_model=AuditPage)
async def list_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    event_prefix: str | None = Query(None, description="e.g. 'posts' or 'auth.login'"),
    actor_id: int | None = Query(None),
    session: AsyncSession = Depends(db_session),
) -> AuditPage:
    offset = (page - 1) * page_size
    repo = AuditRepository(session)
    rows = await repo.list_paginated(
        limit=page_size,
        offset=offset,
        event_prefix=event_prefix,
        actor_id=actor_id,
    )
    total = await repo.count(event_prefix=event_prefix, actor_id=actor_id)
    return AuditPage(
        items=[AuditEntry.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )

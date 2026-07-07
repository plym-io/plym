from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session, require_admin
from plym.models.submission import SubmissionPage, SubmissionReceipt
from plym.service.submission_service import SubmissionService

router = APIRouter(tags=["Submissions"])


def _service(session: AsyncSession = Depends(db_session)) -> SubmissionService:
    return SubmissionService(session)


@router.post("/api/collect", response_model=SubmissionReceipt, status_code=201)
async def collect(
    request: Request,
    payload: dict[str, Any] = Body(...),
    service: SubmissionService = Depends(_service),
) -> SubmissionReceipt:
    return await service.collect(
        payload=payload,
        user_agent=request.headers.get("user-agent"),
        forwarded_for=request.headers.get("x-forwarded-for"),
        peer=request.client.host if request.client else None,
    )


@router.get(
    "/api/submissions",
    response_model=SubmissionPage,
    dependencies=[Depends(require_admin)],
)
async def list_submissions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: SubmissionService = Depends(_service),
) -> SubmissionPage:
    return await service.list_paginated(page=page, page_size=page_size)

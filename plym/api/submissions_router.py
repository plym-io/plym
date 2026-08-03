import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session, require_admin
from plym.models.submission import SubmissionPage, SubmissionReceipt
from plym.service.submission_service import (
    FixedWindowRateLimiter,
    SubmissionMalformedError,
    SubmissionRateLimitedError,
    SubmissionService,
    SubmissionTooLargeError,
    client_ip,
)
from plym.settings import settings

router = APIRouter(tags=["Submissions"])

_limiter = FixedWindowRateLimiter(
    limit=settings.submission_rate_limit,
    window_seconds=settings.submission_rate_window_seconds,
    max_clients=settings.submission_rate_max_clients,
)

_COLLECT_BODY = {
    "required": True,
    "content": {"application/json": {"schema": {"type": "object"}}},
}


def _service(session: AsyncSession = Depends(db_session)) -> SubmissionService:
    return SubmissionService(session)


async def _read_json_object(request: Request) -> dict[str, Any]:
    limit = settings.submission_max_bytes
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise SubmissionTooLargeError(limit)
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise SubmissionTooLargeError(limit)
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SubmissionMalformedError() from exc
    if not isinstance(payload, dict):
        raise SubmissionMalformedError()
    return payload


@router.post(
    "/api/collect",
    response_model=SubmissionReceipt,
    status_code=201,
    openapi_extra={"requestBody": _COLLECT_BODY},
)
async def collect(
    request: Request,
    service: SubmissionService = Depends(_service),
) -> SubmissionReceipt:
    address = client_ip(
        request.headers.get("x-forwarded-for"),
        request.client.host if request.client else None,
        settings.trusted_proxy_hops,
    )
    retry_after = _limiter.hit(address or "unknown", time.monotonic())
    if retry_after > 0:
        raise SubmissionRateLimitedError(retry_after)
    return await service.collect(
        payload=await _read_json_object(request),
        user_agent=request.headers.get("user-agent"),
        client_addr=address,
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

from fastapi import APIRouter, Depends, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import CurrentUser, current_user, db_session, require_editor
from plym.api.state import site_config
from plym.config.site import SiteConfig
from plym.models.media import MediaItem
from plym.service.media_service import MediaService

router = APIRouter(prefix="/api/media", tags=["Media"])


class MediaPage(BaseModel):
    items: list[MediaItem]
    total: int
    page: int
    page_size: int


def _service(
    session: AsyncSession = Depends(db_session),
    site: SiteConfig = Depends(site_config),
) -> MediaService:
    return MediaService(session, site)


@router.post("", response_model=MediaItem, status_code=201, dependencies=[Depends(require_editor)])
async def upload_media(
    file: UploadFile,
    user: CurrentUser = Depends(current_user),
    service: MediaService = Depends(_service),
) -> MediaItem:
    data = await file.read()
    return await service.upload(
        uploader_id=user.id,
        original_name=file.filename or "upload",
        data=data,
    )


@router.get("", response_model=MediaPage, dependencies=[Depends(require_editor)])
async def list_media(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: MediaService = Depends(_service),
) -> MediaPage:
    items, total = await service.list_paginated(page=page, page_size=page_size)
    return MediaPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{media_id}", response_model=MediaItem, dependencies=[Depends(require_editor)])
async def get_media(media_id: int, service: MediaService = Depends(_service)) -> MediaItem:
    return await service.get(media_id)


@router.delete("/{media_id}", status_code=204, dependencies=[Depends(require_editor)])
async def delete_media(
    media_id: int,
    user: CurrentUser = Depends(current_user),
    service: MediaService = Depends(_service),
) -> None:
    await service.delete(media_id=media_id, requester_id=user.id)

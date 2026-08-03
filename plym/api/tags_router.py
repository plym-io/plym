from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session, require_editor
from plym.models.tag import Tag
from plym.service.tag_service import TagService

router = APIRouter(prefix="/api/tags", tags=["Tags"])


def _service(session: AsyncSession = Depends(db_session)) -> TagService:
    return TagService(session)


@router.get("", response_model=list[Tag])
async def list_tags(service: TagService = Depends(_service)) -> list[Tag]:
    return await service.list()


@router.delete("/{tag_id}", status_code=204, dependencies=[Depends(require_editor)])
async def delete_tag(tag_id: int, service: TagService = Depends(_service)) -> None:
    await service.delete(tag_id)

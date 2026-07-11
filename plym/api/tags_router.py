from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session, require_editor
from plym.models.tag import Tag, TagUpdate
from plym.repository.tag_repository import TagRepository
from plym.service.tag_service import TagService

router = APIRouter(prefix="/api/tags", tags=["Tags"])


@router.get("", response_model=list[Tag])
async def list_tags(session: AsyncSession = Depends(db_session)) -> list[Tag]:
    rows = await TagRepository(session).list_all()
    return [Tag.model_validate(r) for r in rows]


@router.patch("/{tag_id}", response_model=Tag, dependencies=[Depends(require_editor)])
async def update_tag(
    tag_id: int,
    payload: TagUpdate,
    session: AsyncSession = Depends(db_session),
) -> Tag:
    return await TagService(session).update(tag_id, payload)

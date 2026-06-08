from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session
from plym.models.tag import Tag
from plym.repository.tag_repository import TagRepository

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[Tag])
async def list_tags(session: AsyncSession = Depends(db_session)) -> list[Tag]:
    rows = await TagRepository(session).list_all()
    return [Tag.model_validate(r) for r in rows]

from sqlalchemy.ext.asyncio import AsyncSession

from plym.exceptions.tags import TagNotFoundError
from plym.instrumentation.tracer import Traced
from plym.models.tag import Tag, TagUpdate
from plym.render.cache import get_store
from plym.repository.tag_repository import TagRepository


class TagService(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tags = TagRepository(session)

    async def update(self, tag_id: int, payload: TagUpdate) -> Tag:
        fields = payload.model_dump(exclude_unset=True)
        if "weight" not in fields:
            row = await self._tags.get_by_id(tag_id)
            if not row:
                raise TagNotFoundError()
            return Tag.model_validate(row)
        row = await self._tags.set_weight(tag_id, fields["weight"])
        if not row:
            raise TagNotFoundError()
        await self._session.commit()
        get_store().delete_prefix("index:")
        return Tag.model_validate(row)

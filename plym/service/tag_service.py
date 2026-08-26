from sqlalchemy.ext.asyncio import AsyncSession

from plym.exceptions.tags import TagInUseError, TagNotFoundError
from plym.instrumentation.tracer import Traced
from plym.models.tag import Tag
from plym.repository.post_repository import PostRepository
from plym.repository.tag_repository import TagRepository


class TagService(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tags = TagRepository(session)
        self._posts = PostRepository(session)

    async def list(self) -> list[Tag]:
        rows = await self._tags.list_all()
        return [Tag.model_validate(r) for r in rows]

    async def delete(self, tag_id: int) -> None:
        if not await self._tags.get_by_id(tag_id):
            raise TagNotFoundError()
        assigned = await self._posts.count_by_tag(tag_id)
        if assigned:
            raise TagInUseError(assigned)
        await self._tags.delete(tag_id)
        await self._session.commit()

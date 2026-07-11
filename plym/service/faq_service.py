from sqlalchemy.ext.asyncio import AsyncSession

from plym.exceptions.faqs import FaqNotFoundError
from plym.instrumentation.tracer import Traced
from plym.models.faq import Faq, FaqItem
from plym.render.cache import get_store
from plym.repository.faq_repository import FaqRepository


class FaqService(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._faqs = FaqRepository(session)

    async def list(self) -> list[Faq]:
        rows = await self._faqs.list_all()
        return [Faq.model_validate(r) for r in rows]

    async def get(self, faq_id: int) -> Faq:
        row = await self._faqs.get_by_id(faq_id)
        if not row:
            raise FaqNotFoundError()
        return Faq.model_validate(row)

    async def create(self, item: FaqItem) -> Faq:
        row = await self._faqs.create(item)
        await self._session.commit()
        return Faq.model_validate(row)

    async def update(self, faq_id: int, item: FaqItem) -> Faq:
        row = await self._faqs.update(faq_id, item)
        if not row:
            raise FaqNotFoundError()
        await self._session.commit()
        get_store().delete_prefix("index:")
        return Faq.model_validate(row)

    async def delete(self, faq_id: int) -> None:
        if not await self._faqs.delete(faq_id):
            raise FaqNotFoundError()
        await self._session.commit()
        get_store().delete_prefix("index:")

import logging
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from plym.config.site import SiteConfig
from plym.exceptions.faqs import FaqNotFoundError
from plym.instrumentation.tracer import Traced
from plym.models.faq import Faq, FaqItem
from plym.repository.faq_repository import FaqRepository
from plym.repository.post_repository import PostRepository
from plym.service.post_pipeline import PostPipeline

log = logging.getLogger("plym.faqs")

_RENDER_CHUNK = 200


class FaqService(Traced):
    def __init__(self, session: AsyncSession, site: SiteConfig, css: str, prism_js: str) -> None:
        self._session = session
        self._faqs = FaqRepository(session)
        self._posts = PostRepository(session)
        self._pipeline = PostPipeline(site, css, prism_js)

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
        affected = await self._posts.list_published_ids_for_faq(faq_id)
        row = await self._faqs.update(faq_id, item)
        if not row:
            raise FaqNotFoundError()
        await self._session.commit()
        self._pipeline.invalidate_index()
        await self._rerender_posts(affected, "faq update")
        return Faq.model_validate(row)

    async def delete(self, faq_id: int) -> None:
        # The join rows cascade away with the FAQ, so the affected posts must be
        # enumerated before the delete lands.
        affected = await self._posts.list_published_ids_for_faq(faq_id)
        if not await self._faqs.delete(faq_id):
            raise FaqNotFoundError()
        await self._session.commit()
        self._pipeline.invalidate_index()
        await self._rerender_posts(affected, "faq delete")

    async def _rerender_posts(self, post_ids: Sequence[int], reason: str) -> None:
        if not post_ids:
            return
        after = 0
        while True:
            rows = await self._posts.list_published_full_after(
                after=after, limit=_RENDER_CHUNK, post_ids=post_ids
            )
            if not rows:
                return
            for row in rows:
                try:
                    await self._pipeline.render_row(row)
                except Exception:
                    # Startup reconcile (or an explicit refresh) re-renders whatever
                    # is left stale; the edit itself already succeeded.
                    log.exception("failed to re-render %s after %s", row["slug"], reason)
            after = rows[-1]["id"]
            if len(rows) < _RENDER_CHUNK:
                return

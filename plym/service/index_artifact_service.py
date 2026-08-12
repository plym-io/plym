import logging
from math import ceil

from sqlalchemy.ext.asyncio import AsyncSession

from plym.config.site import SiteConfig
from plym.instrumentation.tracer import Traced
from plym.render.urls import INDEX_PAGE_SEGMENT, index_path
from plym.service.artifact_writer import write_if_changed
from plym.service.post_listing import PostListing
from plym.service.post_pipeline import PostPipeline
from plym.settings import settings

log = logging.getLogger("plym.index")


class IndexArtifactService(Traced):
    def __init__(self, session: AsyncSession, site: SiteConfig, pipeline: PostPipeline) -> None:
        self._listing = PostListing(session)
        self._site = site
        self._pipeline = pipeline

    async def write(self) -> None:
        page_size = self._site.pagination.page_size
        total = await self._listing.count_published()
        pages = max(1, ceil(total / page_size))

        for page in range(1, pages + 1):
            items, _ = await self._listing.published(page=page, page_size=page_size)
            posts = [item.model_dump() for item in items]
            relative = index_path(page)
            await write_if_changed(
                settings.generated_dir / f"{relative}.html",
                self._pipeline.render_index(posts, page=page, pages=pages),
            )
            await write_if_changed(
                settings.generated_dir / f"{relative}.md",
                self._pipeline.render_index_markdown(posts, page=page, pages=pages),
            )

        self._prune_beyond(pages)
        self._pipeline.invalidate_index()

    def _prune_beyond(self, pages: int) -> None:
        directory = settings.generated_dir / INDEX_PAGE_SEGMENT
        if not directory.is_dir():
            return
        for path in directory.iterdir():
            if path.suffix not in (".html", ".md"):
                continue
            if not path.stem.isdigit() or int(path.stem) > pages:
                path.unlink()
        if not any(directory.iterdir()):
            directory.rmdir()

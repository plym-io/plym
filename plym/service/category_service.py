import logging

from sqlalchemy.ext.asyncio import AsyncSession

from plym.config.site import SiteConfig
from plym.db.locks import claim_slug
from plym.exceptions.categories import (
    CategoryConflictError,
    CategoryInUseError,
    CategoryNotFoundError,
    InvalidCategoryNameError,
    ReservedCategoryNameError,
)
from plym.instrumentation.tracer import Traced
from plym.models.category import Category, CategoryCreate, CategoryUpdate
from plym.render.urls import RESERVED_SEGMENTS
from plym.repository.category_repository import CategoryRepository
from plym.repository.post_repository import PostRepository
from plym.service.post_pipeline import PostPipeline
from plym.service.search_index_service import SearchIndexService

log = logging.getLogger("plym.categories")

_RENDER_CHUNK = 200


class CategoryService(Traced):
    def __init__(self, session: AsyncSession, site: SiteConfig, css: str, prism_js: str) -> None:
        self._session = session
        self._site = site
        self._categories = CategoryRepository(session)
        self._posts = PostRepository(session)
        self._pipeline = PostPipeline(site, css, prism_js)

    def _slug_for(self, name: str) -> str:
        slug = self._pipeline.slugify(name)
        if not slug:
            raise InvalidCategoryNameError(name)
        if slug in RESERVED_SEGMENTS:
            raise ReservedCategoryNameError(slug)
        return slug

    async def list(self) -> list[Category]:
        rows = await self._categories.list_all()
        return [Category.model_validate(r) for r in rows]

    async def get(self, category_id: int) -> Category:
        row = await self._categories.get_by_id(category_id)
        if not row:
            raise CategoryNotFoundError()
        return Category.model_validate(row)

    async def create(self, payload: CategoryCreate) -> Category:
        slug = self._slug_for(payload.name)
        await claim_slug(self._session, slug)
        if await self._categories.conflicts(name=payload.name, slug=slug):
            raise CategoryConflictError(payload.name)
        if await self._posts.slug_exists(slug):
            raise CategoryConflictError(payload.name)
        row = await self._categories.create(name=payload.name, slug=slug, weight=payload.weight)
        await self._session.commit()
        return Category.model_validate(row)

    async def update(self, category_id: int, payload: CategoryUpdate) -> Category:
        existing = await self._categories.get_by_id(category_id)
        if not existing:
            raise CategoryNotFoundError()

        fields = payload.model_dump(exclude_unset=True)
        name = fields.get("name")
        if name is None:
            fields.pop("name", None)
        else:
            fields["slug"] = self._slug_for(name)
            if await self._categories.conflicts(
                name=name, slug=fields["slug"], exclude_id=category_id
            ):
                raise CategoryConflictError(name)
            if fields["slug"] != existing["slug"]:
                await claim_slug(self._session, fields["slug"])
            if fields["slug"] != existing["slug"] and await self._posts.slug_exists(fields["slug"]):
                raise CategoryConflictError(name)
        if not fields:
            return Category.model_validate(existing)

        row = await self._categories.update_fields(category_id, fields)
        if not row:
            raise CategoryNotFoundError()
        await self._session.commit()
        self._pipeline.invalidate_index()

        if fields.get("slug", existing["slug"]) != existing["slug"]:
            await self._move_rendered_posts(category_id, existing["slug"])
            await SearchIndexService(self._session, self._site).refresh()
        return Category.model_validate(row)

    async def delete(self, category_id: int) -> None:
        if not await self._categories.get_by_id(category_id):
            raise CategoryNotFoundError()
        assigned = await self._posts.count_by_category(category_id)
        if assigned:
            raise CategoryInUseError(assigned)
        await self._categories.delete(category_id)
        await self._session.commit()
        self._pipeline.invalidate_index()

    async def _move_rendered_posts(self, category_id: int, old_slug: str) -> None:
        after = 0
        while True:
            rows = await self._posts.list_published_full_after(
                after=after, limit=_RENDER_CHUNK, category_id=category_id
            )
            if not rows:
                return
            for row in rows:
                self._pipeline.remove_rendered(row["slug"], old_slug)
                try:
                    await self._pipeline.render_row(row)
                except Exception:
                    log.exception("failed to re-render %s after category rename", row["slug"])
            after = rows[-1]["id"]
            if len(rows) < _RENDER_CHUNK:
                return

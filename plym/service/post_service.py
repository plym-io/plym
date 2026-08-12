from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from plym.config.site import SiteConfig
from plym.db.locks import claim_slug
from plym.exceptions.categories import CategoryNotFoundError
from plym.exceptions.faqs import FaqNotFoundError
from plym.exceptions.posts import PostNotFoundError, ReservedSlugError, SlugConflictError
from plym.instrumentation.tracer import Traced
from plym.models.category import Category
from plym.models.common import PostStatus
from plym.models.faq import Faq
from plym.models.post import Post, PostCreate, PostListItem, PostUpdate
from plym.models.tag import Tag
from plym.models.user import UserPublic
from plym.render.urls import RESERVED_SEGMENTS, path_for_row
from plym.repository.category_repository import CategoryRepository
from plym.repository.faq_repository import FaqRepository
from plym.repository.post_repository import PostRepository
from plym.repository.tag_repository import TagRepository
from plym.service.post_listing import PostListing
from plym.service.post_pipeline import PostPipeline
from plym.service.site_files_service import refresh_site_artifacts


class PostService(Traced):
    def __init__(self, session: AsyncSession, site: SiteConfig, css: str, prism_js: str) -> None:
        self._session = session
        self._site = site
        self._posts = PostRepository(session)
        self._tags = TagRepository(session)
        self._faqs = FaqRepository(session)
        self._categories = CategoryRepository(session)
        self._pipeline = PostPipeline(site, css, prism_js)
        self._listing = PostListing(session)

    def _row_to_post(self, row: dict[str, Any], tags: list[dict[str, Any]]) -> Post:
        author = UserPublic(
            id=row["author_id"],
            display_name=row["display_name"],
            avatar_url=row.get("avatar_url"),
            links=row.get("links") or [],
        )
        category = row.get("category")
        return Post(
            id=row["id"],
            slug=row["slug"],
            path=path_for_row(row),
            title=row["title"],
            status=PostStatus(row["status"]),
            reading_time=row["reading_time"],
            content=row["content"],
            rendered_path=row.get("rendered_path"),
            excerpt=row.get("excerpt"),
            cover=row.get("cover"),
            canonical_url=row.get("canonical_url"),
            weight=row.get("weight"),
            published_at=row.get("published_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            author=author,
            category=Category.model_validate(category) if category else None,
            tags=[Tag.model_validate(t) for t in tags],
            faqs=[Faq.model_validate(f) for f in row.get("faqs") or []],
        )

    async def _ensure_tags(self, names: list[str]) -> list[int]:
        pairs = [(name, self._pipeline.slugify(name)) for name in names]
        slug_to_id = await self._tags.upsert_many(pairs)
        return [slug_to_id[slug] for _, slug in pairs]

    async def _ensure_category(self, category_id: int) -> None:
        if not await self._categories.get_by_id(category_id):
            raise CategoryNotFoundError()

    async def _validate_slug(self, slug: str) -> None:
        if slug in RESERVED_SEGMENTS:
            raise ReservedSlugError(slug)
        # Posts and categories share one URL segment namespace across two tables, so no
        # constraint can enforce it; serialise the claim or two concurrent writers both pass.
        await claim_slug(self._session, slug)
        if await self._posts.slug_exists(slug) or await self._categories.slug_exists(slug):
            raise SlugConflictError(slug)

    async def _sync_faqs(self, post_id: int, faqs: list[int]) -> None:
        ordered = list(dict[str, Any].fromkeys(faqs))
        existing = await self._faqs.existing_ids(ordered)
        if any(fid not in existing for fid in ordered):
            raise FaqNotFoundError()
        await self._faqs.replace_for_post(post_id, ordered)

    async def create(self, author_id: int, payload: PostCreate) -> Post:
        await self._validate_slug(payload.slug)
        if payload.category_id is not None:
            await self._ensure_category(payload.category_id)

        reading_time = self._pipeline.reading_minutes(payload.content)
        post_id = await self._posts.create(
            slug=payload.slug,
            title=payload.title,
            author_id=author_id,
            content=payload.content,
            excerpt=payload.excerpt,
            cover=payload.cover,
            canonical_url=payload.canonical_url,
            reading_time=reading_time,
            weight=payload.weight,
            category_id=payload.category_id,
            published_at=payload.published_at,
        )
        if payload.tags:
            tag_ids = await self._ensure_tags(payload.tags)
            await self._tags.replace_for_post(post_id, tag_ids)
        if payload.faqs:
            await self._sync_faqs(post_id, payload.faqs)
        await self._session.commit()
        self._pipeline.invalidate_index()
        return await self.get(post_id)

    async def update(self, post_id: int, payload: PostUpdate) -> Post:
        existing = await self._posts.get_by_id(post_id)
        if not existing:
            raise PostNotFoundError()
        if payload.slug is not None and payload.slug != existing["slug"]:
            await self._validate_slug(payload.slug)
        fields = payload.model_dump(exclude_unset=True, exclude={"tags"})
        if fields.get("category_id") is not None:
            await self._ensure_category(fields["category_id"])
        if "status" in fields and fields["status"] is not None:
            fields["status"] = fields["status"].value
        if "content" in fields and fields["content"] is not None:
            fields["reading_time"] = self._pipeline.reading_minutes(fields["content"])
        await self._posts.update_fields(post_id, fields)
        if payload.tags is not None:
            tag_ids = await self._ensure_tags(payload.tags)
            await self._tags.replace_for_post(post_id, tag_ids)
        if payload.faqs is not None:
            await self._sync_faqs(post_id, payload.faqs)
        await self._session.commit()

        was_published = existing["status"] == "published"
        is_published = fields.get("status", existing["status"]) == "published"
        slug_changed = "slug" in fields and fields["slug"] != existing["slug"]
        old_category = (existing.get("category") or {}).get("slug")
        category_changed = (
            "category_id" in fields and fields["category_id"] != existing["category_id"]
        )
        url_changed = slug_changed or category_changed

        self._pipeline.invalidate_index()
        if was_published and url_changed:
            self._pipeline.remove_rendered(existing["slug"], old_category)

        if is_published or was_published:
            post = await self.refresh(post_id)
            await refresh_site_artifacts(self._session, self._site, self._pipeline)
            return post
        return await self.get(post_id)

    async def get(self, post_id: int) -> Post:
        row = await self._posts.get_by_id(post_id)
        if not row:
            raise PostNotFoundError()
        return self._row_to_post(row, row["tags"])

    async def get_by_slug(self, slug: str) -> Post:
        row = await self._posts.get_by_slug(slug)
        if not row:
            raise PostNotFoundError()
        return self._row_to_post(row, row["tags"])

    async def list_published(self, *, page: int, page_size: int) -> tuple[list[PostListItem], int]:
        return await self._listing.published(page=page, page_size=page_size)

    async def list_all(
        self,
        *,
        page: int,
        page_size: int,
        status: PostStatus | None = None,
        search: str | None = None,
    ) -> tuple[list[PostListItem], int]:
        offset = max(0, (page - 1) * page_size)
        status_value = status.value if status else None
        rows = await self._posts.list_all_paginated(
            limit=page_size, offset=offset, status=status_value, search=search
        )
        total = (
            int(rows[0]["total"])
            if rows
            else await self._posts.count_all(status=status_value, search=search)
        )
        return await self._listing.with_tags(rows), total

    async def refresh(self, post_id: int) -> Post:
        post = await self.get(post_id)
        category = post.category.model_dump() if post.category else None
        if post.status is not PostStatus.PUBLISHED:
            self._pipeline.remove_rendered(post.slug, post.category.slug if post.category else None)
            await self._posts.set_rendered_path(post.id, "")
            await self._session.commit()
            return await self.get(post_id)
        result = await self._pipeline.render_and_persist(
            slug=post.slug,
            title=post.title,
            content=post.content,
            excerpt=post.excerpt,
            cover=post.cover,
            canonical_url=post.canonical_url,
            author={
                "display_name": post.author.display_name,
                "avatar_url": post.author.avatar_url,
                "links": [link.model_dump() for link in post.author.links],
            },
            published_at=post.published_at,
            updated_at=post.updated_at,
            tags=[t.model_dump() for t in post.tags],
            faqs=[f.model_dump() for f in post.faqs],
            category=category,
        )
        await self._posts.set_rendered_path(post.id, result.rendered_path or "")
        await self._posts.update_fields(post.id, {"reading_time": result.reading_time})
        await self._session.commit()
        self._pipeline.invalidate_index()
        return await self.get(post_id)

    async def delete(self, post_id: int) -> None:
        post = await self.get(post_id)
        was_published = post.status is PostStatus.PUBLISHED
        await self._posts.delete(post_id)
        await self._session.commit()
        self._pipeline.remove_rendered(post.slug, post.category.slug if post.category else None)
        self._pipeline.invalidate_index()
        if was_published:
            await refresh_site_artifacts(self._session, self._site, self._pipeline)

    def preview(
        self,
        *,
        title: str,
        content: str,
        excerpt: str | None,
        cover: str | None,
        canonical_url: str | None = None,
    ) -> str:
        return self._pipeline.render_preview(
            title=title,
            content=content,
            excerpt=excerpt,
            cover=cover,
            canonical_url=canonical_url,
        )

    def render_index(self, posts: list[dict[str, Any]], page: int = 1, pages: int = 1) -> str:
        return self._pipeline.render_index(posts, page=page, pages=pages)

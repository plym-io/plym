from sqlalchemy.ext.asyncio import AsyncSession

from plym.config.site import SiteConfig
from plym.exceptions.posts import PostNotFoundError, SlugConflictError
from plym.instrumentation.tracer import Traced
from plym.models.common import PostStatus
from plym.models.post import Post, PostCreate, PostListItem, PostUpdate
from plym.models.tag import Tag
from plym.models.user import UserPublic
from plym.repository.post_repository import PostRepository
from plym.repository.tag_repository import TagRepository
from plym.service.post_pipeline import PostPipeline


class PostService(Traced):
    def __init__(self, session: AsyncSession, site: SiteConfig, css: str, prism_js: str) -> None:
        self._session = session
        self._site = site
        self._posts = PostRepository(session)
        self._tags = TagRepository(session)
        self._pipeline = PostPipeline(site, css, prism_js)

    def _row_to_post(self, row: dict, tags: list[dict]) -> Post:
        author = UserPublic(
            id=row["author_id"],
            display_name=row["display_name"],
            avatar_url=row.get("avatar_url"),
        )
        return Post(
            id=row["id"],
            slug=row["slug"],
            title=row["title"],
            status=PostStatus(row["status"]),
            reading_time=row["reading_time"],
            content=row["content"],
            rendered_path=row.get("rendered_path"),
            excerpt=row.get("excerpt"),
            cover=row.get("cover"),
            canonical_url=row.get("canonical_url"),
            published_at=row.get("published_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            author=author,
            tags=[Tag.model_validate(t) for t in tags],
        )

    async def _ensure_tags(self, names: list[str]) -> list[int]:
        pairs = [(name, self._pipeline.slugify(name)) for name in names]
        slug_to_id = await self._tags.upsert_many(pairs)
        return [slug_to_id[slug] for _, slug in pairs]

    async def create(self, author_id: int, payload: PostCreate) -> Post:
        if await self._posts.slug_exists(payload.slug):
            raise SlugConflictError(payload.slug)

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
        )
        if payload.tags:
            tag_ids = await self._ensure_tags(payload.tags)
            await self._tags.replace_for_post(post_id, tag_ids)
        await self._session.commit()
        self._pipeline.invalidate_index()
        return await self.get(post_id)

    async def update(self, post_id: int, payload: PostUpdate) -> Post:
        existing = await self._posts.get_by_id(post_id)
        if not existing:
            raise PostNotFoundError()
        if (
            payload.slug is not None
            and payload.slug != existing["slug"]
            and await self._posts.slug_exists(payload.slug)
        ):
            raise SlugConflictError(payload.slug)
        fields = payload.model_dump(exclude_unset=True, exclude={"tags"})
        if "status" in fields and fields["status"] is not None:
            fields["status"] = fields["status"].value
        if "content" in fields and fields["content"] is not None:
            fields["reading_time"] = self._pipeline.reading_minutes(fields["content"])
        await self._posts.update_fields(post_id, fields)
        if payload.tags is not None:
            tag_ids = await self._ensure_tags(payload.tags)
            await self._tags.replace_for_post(post_id, tag_ids)
        await self._session.commit()

        new_status = fields.get("status")
        was_published = existing["status"] == "published"
        is_unpublishing = new_status is not None and new_status != "published" and was_published
        slug_changed = "slug" in fields and fields["slug"] != existing["slug"]
        if is_unpublishing:
            self._pipeline.remove_rendered(existing["slug"])
        else:
            if slug_changed and was_published:
                self._pipeline.remove_rendered(existing["slug"])
            self._pipeline.invalidate_index()
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

    def _to_list_item(self, r: dict, tags: list[dict]) -> PostListItem:
        author = UserPublic(
            id=r["author_id"],
            display_name=r["display_name"],
            avatar_url=r.get("avatar_url"),
        )
        return PostListItem(
            id=r["id"],
            slug=r["slug"],
            title=r["title"],
            status=PostStatus(r["status"]),
            reading_time=r["reading_time"],
            excerpt=r.get("excerpt"),
            cover=r.get("cover"),
            canonical_url=r.get("canonical_url"),
            published_at=r.get("published_at"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            author=author,
            tags=[Tag.model_validate(t) for t in tags],
        )

    async def _items_with_tags(self, rows: list[dict]) -> list[PostListItem]:
        tags_by_post = await self._tags.list_for_posts([r["id"] for r in rows])
        return [self._to_list_item(r, tags_by_post.get(r["id"], [])) for r in rows]

    async def list_published(self, *, page: int, page_size: int) -> tuple[list[PostListItem], int]:
        offset = max(0, (page - 1) * page_size)
        rows = await self._posts.list_published(limit=page_size, offset=offset)
        total = int(rows[0]["total"]) if rows else await self._posts.count_published()
        return await self._items_with_tags(rows), total

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
        return await self._items_with_tags(rows), total

    async def refresh(self, post_id: int) -> Post:
        post = await self.get(post_id)
        result = await self._pipeline.render_and_persist(
            slug=post.slug,
            title=post.title,
            content=post.content,
            excerpt=post.excerpt,
            cover=post.cover,
            canonical_url=post.canonical_url,
            author={"display_name": post.author.display_name, "avatar_url": post.author.avatar_url},
            published_at=post.published_at,
            updated_at=post.updated_at,
            tags=[t.model_dump() for t in post.tags],
        )
        await self._posts.set_rendered_path(post.id, result.rendered_path or "")
        await self._posts.update_fields(post.id, {"reading_time": result.reading_time})
        await self._session.commit()
        self._pipeline.invalidate_index()
        return await self.get(post_id)

    async def delete(self, post_id: int) -> None:
        post = await self.get(post_id)
        await self._posts.delete(post_id)
        await self._session.commit()
        self._pipeline.remove_rendered(post.slug)

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

    def render_index(self, posts: list[dict]) -> str:
        return self._pipeline.render_index(posts)

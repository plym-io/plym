from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from plym.instrumentation.tracer import Traced
from plym.models.category import Category
from plym.models.common import PostStatus
from plym.models.post import PostListItem
from plym.models.tag import Tag
from plym.models.user import UserPublic
from plym.render.urls import path_for_row
from plym.repository.post_repository import PostRepository
from plym.repository.tag_repository import TagRepository


def to_list_item(row: dict[str, Any], tags: list[dict[str, Any]]) -> PostListItem:
    author = UserPublic(
        id=row["author_id"],
        display_name=row["display_name"],
        avatar_url=row.get("avatar_url"),
        links=row.get("links") or [],
    )
    category = row.get("category")
    return PostListItem(
        id=row["id"],
        slug=row["slug"],
        path=path_for_row(row),
        title=row["title"],
        status=PostStatus(row["status"]),
        reading_time=row["reading_time"],
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
    )


class PostListing(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._posts = PostRepository(session)
        self._tags = TagRepository(session)

    async def with_tags(self, rows: list[dict[str, Any]]) -> list[PostListItem]:
        tags_by_post = await self._tags.list_for_posts([r["id"] for r in rows])
        return [to_list_item(r, tags_by_post.get(r["id"], [])) for r in rows]

    async def published(self, *, page: int, page_size: int) -> tuple[list[PostListItem], int]:
        offset = max(0, (page - 1) * page_size)
        rows = await self._posts.list_published(limit=page_size, offset=offset)
        total = int(rows[0]["total"]) if rows else await self._posts.count_published()
        return await self.with_tags(rows), total

    async def count_published(self) -> int:
        return await self._posts.count_published()

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from plym.exceptions.posts import SlugConflictError


class PostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def slug_exists(self, slug: str) -> bool:
        result = await self._session.execute(
            text("SELECT 1 FROM public.pl_posts WHERE slug = :slug"),
            {"slug": slug},
        )
        return result.first() is not None

    async def create(
        self,
        *,
        slug: str,
        title: str,
        author_id: int,
        content: str,
        excerpt: str | None,
        cover: str | None,
        canonical_url: str | None,
        reading_time: int,
    ) -> int:
        try:
            result = await self._session.execute(
                text(
                    """
                    INSERT INTO public.pl_posts
                        (slug, title, author_id, content, excerpt, cover,
                         canonical_url, reading_time)
                    VALUES (:slug, :title, :author_id, :content, :excerpt, :cover,
                            :canonical_url, :reading_time)
                    RETURNING id
                    """
                ),
                {
                    "slug": slug,
                    "title": title,
                    "author_id": author_id,
                    "content": content,
                    "excerpt": excerpt,
                    "cover": cover,
                    "canonical_url": canonical_url,
                    "reading_time": reading_time,
                },
            )
            return int(result.scalar_one())
        except IntegrityError as e:
            raise SlugConflictError(slug) from e

    _UPDATABLE_FIELDS = {
        "title", "content", "excerpt", "cover", "canonical_url", "status", "reading_time"
    }

    async def update_fields(self, post_id: int, fields: dict) -> None:
        assignable = {k: v for k, v in fields.items() if k in self._UPDATABLE_FIELDS}
        if not assignable:
            return
        set_clause = ", ".join(f"{k} = :{k}" for k in assignable)
        await self._session.execute(
            text(f"UPDATE public.pl_posts SET {set_clause} WHERE id = :id"),
            {**assignable, "id": post_id},
        )

    async def set_rendered_path(self, post_id: int, path: str) -> None:
        await self._session.execute(
            text("UPDATE public.pl_posts SET rendered_path = :p WHERE id = :id"),
            {"p": path, "id": post_id},
        )

    async def get_by_id(self, post_id: int) -> dict | None:
        result = await self._session.execute(
            text(
                """
                SELECT p.*, u.display_name, u.avatar_url
                FROM public.pl_posts p
                JOIN public.pl_users u ON u.id = p.author_id
                WHERE p.id = :id
                """
            ),
            {"id": post_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_by_slug(self, slug: str) -> dict | None:
        result = await self._session.execute(
            text(
                """
                SELECT p.*, u.display_name, u.avatar_url
                FROM public.pl_posts p
                JOIN public.pl_users u ON u.id = p.author_id
                WHERE p.slug = :slug
                """
            ),
            {"slug": slug},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def list_published(self, *, limit: int, offset: int) -> list[dict]:
        result = await self._session.execute(
            text(
                """
                SELECT p.id, p.slug, p.title, p.status, p.reading_time, p.excerpt,
                       p.cover, p.canonical_url, p.published_at, p.created_at, p.updated_at,
                       u.id AS author_id, u.display_name, u.avatar_url
                FROM public.pl_posts p
                JOIN public.pl_users u ON u.id = p.author_id
                WHERE p.status = 'published'
                ORDER BY p.published_at DESC NULLS LAST, p.id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        )
        return [dict(r) for r in result.mappings().all()]

    async def count_published(self) -> int:
        result = await self._session.execute(
            text("SELECT COUNT(*) FROM public.pl_posts WHERE status = 'published'")
        )
        return int(result.scalar_one())

    async def delete(self, post_id: int) -> None:
        await self._session.execute(
            text("DELETE FROM public.pl_posts WHERE id = :id"),
            {"id": post_id},
        )

    async def list_all_paginated(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        search: str | None = None,
    ) -> list[dict]:
        conditions: list[str] = []
        params: dict = {"limit": limit, "offset": offset}
        if status:
            conditions.append("p.status = :status")
            params["status"] = status
        if search:
            conditions.append("(p.title ILIKE :search OR p.slug ILIKE :search)")
            params["search"] = f"%{search}%"
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        result = await self._session.execute(
            text(
                f"""
                SELECT p.id, p.slug, p.title, p.status, p.reading_time, p.excerpt,
                       p.cover, p.canonical_url, p.published_at, p.created_at, p.updated_at,
                       u.id AS author_id, u.display_name, u.avatar_url
                FROM public.pl_posts p
                JOIN public.pl_users u ON u.id = p.author_id
                {where}
                ORDER BY p.updated_at DESC, p.id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
        return [dict(r) for r in result.mappings().all()]

    async def count_all(self, *, status: str | None = None, search: str | None = None) -> int:
        conditions: list[str] = []
        params: dict = {}
        if status:
            conditions.append("status = :status")
            params["status"] = status
        if search:
            conditions.append("(title ILIKE :search OR slug ILIKE :search)")
            params["search"] = f"%{search}%"
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        result = await self._session.execute(
            text(f"SELECT COUNT(*) FROM public.pl_posts {where}"), params
        )
        return int(result.scalar_one())

    async def find_references_to_filename(self, filename: str) -> list[dict]:
        pattern = f"%{filename}%"
        result = await self._session.execute(
            text(
                """
                SELECT id, slug, title
                FROM public.pl_posts
                WHERE content LIKE :p OR cover LIKE :p
                ORDER BY id
                """
            ),
            {"p": pattern},
        )
        return [dict(r) for r in result.mappings().all()]

    async def list_all_for_backup(self) -> list[dict]:
        result = await self._session.execute(
            text(
                """
                SELECT id, slug, title, author_id, status, reading_time, content,
                       rendered_path, excerpt, cover, published_at,
                       created_at, updated_at
                FROM public.pl_posts
                ORDER BY id
                """
            )
        )
        return [dict(r) for r in result.mappings().all()]

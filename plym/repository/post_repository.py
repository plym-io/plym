import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from plym.exceptions.posts import SlugConflictError
from plym.instrumentation.tracer import Traced

_TAGS_JSON = """
        COALESCE((
            SELECT json_agg(json_build_object('id', t.id, 'name', t.name, 'slug', t.slug)
                            ORDER BY t.name)
            FROM public.pl_post_tags pt
            JOIN public.pl_tags t ON t.id = pt.tag_id
            WHERE pt.post_id = p.id
        ), '[]'::json) AS tags
"""

_CATEGORY_JSON = """
        (
            SELECT json_build_object('id', c.id, 'name', c.name, 'slug', c.slug,
                                     'weight', c.weight)
            FROM public.pl_categories c
            WHERE c.id = p.category_id
        ) AS category
"""

_FAQS_JSON = """
        COALESCE((
            SELECT json_agg(json_build_object('id', f.id,
                                              'question', f.data->>'question',
                                              'answer', f.data->>'answer')
                            ORDER BY pf.position)
            FROM public.pl_post_faqs pf
            JOIN public.pl_faqs f ON f.id = pf.faq_id
            WHERE pf.post_id = p.id
        ), '[]'::json) AS faqs
"""


def _decode_json_col(data: dict[str, Any], key: str) -> None:
    value = data.get(key)
    if isinstance(value, str):
        data[key] = json.loads(value)


def _with_json(row: RowMapping) -> dict[str, Any]:
    data = dict(row)
    _decode_json_col(data, "tags")
    _decode_json_col(data, "faqs")
    _decode_json_col(data, "links")
    _decode_json_col(data, "category")
    return data


class PostRepository(Traced):
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
        weight: int | None = None,
        category_id: int | None = None,
    ) -> int:
        try:
            result = await self._session.execute(
                text(
                    """
                    INSERT INTO public.pl_posts
                        (slug, title, author_id, content, excerpt, cover,
                         canonical_url, reading_time, weight, category_id)
                    VALUES (:slug, :title, :author_id, :content, :excerpt, :cover,
                            :canonical_url, :reading_time, :weight, :category_id)
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
                    "weight": weight,
                    "category_id": category_id,
                },
            )
            return int(result.scalar_one())
        except IntegrityError as e:
            raise SlugConflictError(slug) from e

    _UPDATABLE_FIELDS = {
        "slug",
        "title",
        "content",
        "excerpt",
        "cover",
        "canonical_url",
        "status",
        "reading_time",
        "weight",
        "category_id",
    }

    async def update_fields(self, post_id: int, fields: dict[str, Any]) -> None:
        assignable = {k: v for k, v in fields.items() if k in self._UPDATABLE_FIELDS}
        if not assignable:
            return
        set_clause = ", ".join(f"{k} = :{k}" for k in assignable)
        try:
            await self._session.execute(
                text(f"UPDATE public.pl_posts SET {set_clause} WHERE id = :id"),
                {**assignable, "id": post_id},
            )
        except IntegrityError as e:
            if "slug" in assignable:
                raise SlugConflictError(assignable["slug"]) from e
            raise

    async def set_rendered_path(self, post_id: int, path: str) -> None:
        await self._session.execute(
            text("UPDATE public.pl_posts SET rendered_path = :p WHERE id = :id"),
            {"p": path, "id": post_id},
        )

    async def get_by_id(self, post_id: int) -> dict[str, Any] | None:
        result = await self._session.execute(
            text(
                f"""
                SELECT p.*, u.display_name, u.avatar_url,
                       COALESCE(u.links, '[]'::jsonb) AS links,
                {_TAGS_JSON},
                {_FAQS_JSON},
                {_CATEGORY_JSON}
                FROM public.pl_posts p
                JOIN public.pl_users u ON u.id = p.author_id
                WHERE p.id = :id
                """
            ),
            {"id": post_id},
        )
        row = result.mappings().first()
        return _with_json(row) if row else None

    async def get_by_slug(self, slug: str) -> dict[str, Any] | None:
        result = await self._session.execute(
            text(
                f"""
                SELECT p.*, u.display_name, u.avatar_url,
                       COALESCE(u.links, '[]'::jsonb) AS links,
                {_TAGS_JSON},
                {_FAQS_JSON},
                {_CATEGORY_JSON}
                FROM public.pl_posts p
                JOIN public.pl_users u ON u.id = p.author_id
                WHERE p.slug = :slug
                """
            ),
            {"slug": slug},
        )
        row = result.mappings().first()
        return _with_json(row) if row else None

    async def list_published(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text(
                f"""
                SELECT p.id, p.slug, p.title, p.status, p.reading_time, p.excerpt,
                       p.cover, p.canonical_url, p.weight, p.category_id,
                       p.published_at, p.created_at, p.updated_at,
                       u.id AS author_id, u.display_name, u.avatar_url,
                       COALESCE(u.links, '[]'::jsonb) AS links,
                       COUNT(*) OVER() AS total,
                {_CATEGORY_JSON}
                FROM public.pl_posts p
                JOIN public.pl_users u ON u.id = p.author_id
                WHERE p.status = 'published'
                ORDER BY p.weight ASC NULLS LAST, p.published_at DESC NULLS LAST, p.id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        )
        return [_with_json(r) for r in result.mappings().all()]

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
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
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
                       p.cover, p.canonical_url, p.weight, p.category_id,
                       p.published_at, p.created_at, p.updated_at,
                       u.id AS author_id, u.display_name, u.avatar_url,
                       COALESCE(u.links, '[]'::jsonb) AS links,
                       COUNT(*) OVER() AS total,
                {_CATEGORY_JSON}
                FROM public.pl_posts p
                JOIN public.pl_users u ON u.id = p.author_id
                {where}
                ORDER BY p.updated_at DESC, p.id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
        return [_with_json(r) for r in result.mappings().all()]

    async def count_all(self, *, status: str | None = None, search: str | None = None) -> int:
        conditions: list[str] = []
        params: dict[str, Any] = {}
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

    async def find_references_to_filename(
        self, filename: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        pattern = f"%{filename}%"
        result = await self._session.execute(
            text(
                """
                SELECT id, slug, title
                FROM public.pl_posts
                WHERE content LIKE :p OR cover LIKE :p
                ORDER BY id
                LIMIT :limit
                """
            ),
            {"p": pattern, "limit": limit},
        )
        return [dict(r) for r in result.mappings().all()]

    async def list_for_backup_after(self, *, after: int, limit: int) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text(
                """
                SELECT p.id, p.slug, p.title, p.author_id, p.status, p.reading_time,
                       p.content, p.rendered_path, p.excerpt, p.cover, p.weight,
                       p.category_id, c.slug AS category_slug,
                       p.published_at, p.created_at, p.updated_at
                FROM public.pl_posts p
                LEFT JOIN public.pl_categories c ON c.id = p.category_id
                WHERE p.id > :after
                ORDER BY p.id
                LIMIT :limit
                """
            ),
            {"after": after, "limit": limit},
        )
        return [dict(r) for r in result.mappings().all()]

    async def list_published_slugs_after(self, *, after: int, limit: int) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text(
                """
                SELECT p.id, p.slug, p.updated_at, p.published_at, c.slug AS category_slug
                FROM public.pl_posts p
                LEFT JOIN public.pl_categories c ON c.id = p.category_id
                WHERE p.status = 'published' AND p.id > :after
                ORDER BY p.id
                LIMIT :limit
                """
            ),
            {"after": after, "limit": limit},
        )
        return [dict(r) for r in result.mappings().all()]

    async def list_published_meta_after(self, *, after: int, limit: int) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text(
                """
                SELECT p.id, p.slug, p.title, p.excerpt, c.slug AS category_slug
                FROM public.pl_posts p
                LEFT JOIN public.pl_categories c ON c.id = p.category_id
                WHERE p.status = 'published' AND p.id > :after
                ORDER BY p.id
                LIMIT :limit
                """
            ),
            {"after": after, "limit": limit},
        )
        return [dict(r) for r in result.mappings().all()]

    async def list_published_ids_for_faq(self, faq_id: int) -> list[int]:
        result = await self._session.execute(
            text(
                """
                SELECT p.id
                FROM public.pl_posts p
                JOIN public.pl_post_faqs pf ON pf.post_id = p.id
                WHERE pf.faq_id = :faq_id AND p.status = 'published'
                ORDER BY p.id
                """
            ),
            {"faq_id": faq_id},
        )
        return [int(r[0]) for r in result]

    async def list_published_full_after(
        self,
        *,
        after: int,
        limit: int,
        category_id: int | None = None,
        author_id: int | None = None,
        post_ids: Sequence[int] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"after": after, "limit": limit}
        scopes: list[str] = []
        if category_id is not None:
            scopes.append("AND p.category_id = :category_id")
            params["category_id"] = category_id
        if author_id is not None:
            scopes.append("AND p.author_id = :author_id")
            params["author_id"] = author_id
        if post_ids is not None:
            scopes.append("AND p.id = ANY(CAST(:post_ids AS BIGINT[]))")
            params["post_ids"] = list(post_ids)
        scope = " ".join(scopes)
        result = await self._session.execute(
            text(
                f"""
                SELECT p.*, u.display_name, u.avatar_url,
                       COALESCE(u.links, '[]'::jsonb) AS links,
                {_TAGS_JSON},
                {_FAQS_JSON},
                {_CATEGORY_JSON}
                FROM public.pl_posts p
                JOIN public.pl_users u ON u.id = p.author_id
                WHERE p.status = 'published' AND p.id > :after {scope}
                ORDER BY p.id
                LIMIT :limit
                """
            ),
            params,
        )
        return [_with_json(r) for r in result.mappings().all()]

    async def list_published_for_index_after(
        self, *, after: int, limit: int
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text(
                f"""
                SELECT p.id, p.slug, p.title, p.excerpt, p.content, p.reading_time,
                       p.published_at, p.updated_at,
                       u.display_name, c.slug AS category_slug,
                {_TAGS_JSON}
                FROM public.pl_posts p
                JOIN public.pl_users u ON u.id = p.author_id
                LEFT JOIN public.pl_categories c ON c.id = p.category_id
                WHERE p.status = 'published' AND p.id > :after
                ORDER BY p.id
                LIMIT :limit
                """
            ),
            {"after": after, "limit": limit},
        )
        return [_with_json(r) for r in result.mappings().all()]

    async def count_by_category(self, category_id: int) -> int:
        result = await self._session.execute(
            text("SELECT COUNT(*) FROM public.pl_posts WHERE category_id = :id"),
            {"id": category_id},
        )
        return int(result.scalar_one())

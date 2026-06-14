from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plym.instrumentation.tracer import Traced


class TagRepository(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(self, tags: list[tuple[str, str]]) -> dict[str, int]:
        if not tags:
            return {}
        by_slug = {slug: name for name, slug in tags}
        result = await self._session.execute(
            text(
                """
                INSERT INTO public.pl_tags (name, slug)
                SELECT * FROM UNNEST(CAST(:names AS TEXT[]), CAST(:slugs AS TEXT[]))
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                RETURNING slug, id
                """
            ),
            {"names": list(by_slug.values()), "slugs": list(by_slug.keys())},
        )
        return {row["slug"]: int(row["id"]) for row in result.mappings().all()}

    async def list_all(self) -> list[dict]:
        result = await self._session.execute(
            text("SELECT id, name, slug FROM public.pl_tags ORDER BY name")
        )
        return [dict(r) for r in result.mappings().all()]

    async def list_for_posts(self, post_ids: list[int]) -> dict[int, list[dict]]:
        if not post_ids:
            return {}
        result = await self._session.execute(
            text(
                """
                SELECT pt.post_id, t.id, t.name, t.slug
                FROM public.pl_tags t
                JOIN public.pl_post_tags pt ON pt.tag_id = t.id
                WHERE pt.post_id = ANY(CAST(:ids AS BIGINT[]))
                ORDER BY t.name
                """
            ),
            {"ids": post_ids},
        )
        grouped: dict[int, list[dict]] = {}
        for row in result.mappings().all():
            grouped.setdefault(row["post_id"], []).append(
                {"id": row["id"], "name": row["name"], "slug": row["slug"]}
            )
        return grouped

    async def replace_for_post(self, post_id: int, tag_ids: list[int]) -> None:
        await self._session.execute(
            text("DELETE FROM public.pl_post_tags WHERE post_id = :id"),
            {"id": post_id},
        )
        if not tag_ids:
            return
        await self._session.execute(
            text(
                "INSERT INTO public.pl_post_tags (post_id, tag_id) "
                "SELECT :post_id, UNNEST(CAST(:tag_ids AS BIGINT[]))"
            ),
            {"post_id": post_id, "tag_ids": tag_ids},
        )

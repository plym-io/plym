from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class TagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, name: str, slug: str) -> int:
        result = await self._session.execute(
            text(
                """
                INSERT INTO public.pl_tags (name, slug)
                VALUES (:name, :slug)
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """
            ),
            {"name": name, "slug": slug},
        )
        return int(result.scalar_one())

    async def list_all(self) -> list[dict]:
        result = await self._session.execute(
            text("SELECT id, name, slug FROM public.pl_tags ORDER BY name")
        )
        return [dict(r) for r in result.mappings().all()]

    async def list_for_post(self, post_id: int) -> list[dict]:
        result = await self._session.execute(
            text(
                """
                SELECT t.id, t.name, t.slug
                FROM public.pl_tags t
                JOIN public.pl_post_tags pt ON pt.tag_id = t.id
                WHERE pt.post_id = :id
                ORDER BY t.name
                """
            ),
            {"id": post_id},
        )
        return [dict(r) for r in result.mappings().all()]

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

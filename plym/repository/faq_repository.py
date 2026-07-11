from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plym.instrumentation.tracer import Traced
from plym.models.faq import FaqItem

_FAQ_COLUMNS = "id, data->>'question' AS question, data->>'answer' AS answer"


class FaqRepository(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, item: FaqItem) -> dict:
        result = await self._session.execute(
            text(
                f"""
                INSERT INTO public.pl_faqs (data)
                VALUES (jsonb_build_object(
                    'question', CAST(:question AS TEXT), 'answer', CAST(:answer AS TEXT)))
                RETURNING {_FAQ_COLUMNS}
                """
            ),
            {"question": item.question, "answer": item.answer},
        )
        return dict(result.mappings().one())

    async def list_all(self) -> list[dict]:
        result = await self._session.execute(
            text(f"SELECT {_FAQ_COLUMNS} FROM public.pl_faqs ORDER BY id")
        )
        return [dict(r) for r in result.mappings().all()]

    async def get_by_id(self, faq_id: int) -> dict | None:
        result = await self._session.execute(
            text(f"SELECT {_FAQ_COLUMNS} FROM public.pl_faqs WHERE id = :id"),
            {"id": faq_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def update(self, faq_id: int, item: FaqItem) -> dict | None:
        result = await self._session.execute(
            text(
                f"""
                UPDATE public.pl_faqs
                SET data = jsonb_build_object(
                    'question', CAST(:question AS TEXT), 'answer', CAST(:answer AS TEXT))
                WHERE id = :id
                RETURNING {_FAQ_COLUMNS}
                """
            ),
            {"id": faq_id, "question": item.question, "answer": item.answer},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def delete(self, faq_id: int) -> bool:
        result = await self._session.execute(
            text("DELETE FROM public.pl_faqs WHERE id = :id RETURNING id"),
            {"id": faq_id},
        )
        return result.first() is not None

    async def existing_ids(self, faq_ids: list[int]) -> set[int]:
        if not faq_ids:
            return set()
        result = await self._session.execute(
            text("SELECT id FROM public.pl_faqs WHERE id = ANY(CAST(:ids AS BIGINT[]))"),
            {"ids": faq_ids},
        )
        return {int(r[0]) for r in result}

    async def list_for_posts(self, post_ids: list[int]) -> dict[int, list[dict]]:
        if not post_ids:
            return {}
        result = await self._session.execute(
            text(
                """
                SELECT pf.post_id, f.id,
                       f.data->>'question' AS question,
                       f.data->>'answer' AS answer
                FROM public.pl_faqs f
                JOIN public.pl_post_faqs pf ON pf.faq_id = f.id
                WHERE pf.post_id = ANY(CAST(:ids AS BIGINT[]))
                ORDER BY pf.position
                """
            ),
            {"ids": post_ids},
        )
        grouped: dict[int, list[dict]] = {}
        for row in result.mappings().all():
            grouped.setdefault(row["post_id"], []).append(
                {"id": row["id"], "question": row["question"], "answer": row["answer"]}
            )
        return grouped

    async def replace_for_post(self, post_id: int, faq_ids: list[int]) -> None:
        await self._session.execute(
            text("DELETE FROM public.pl_post_faqs WHERE post_id = :id"),
            {"id": post_id},
        )
        if not faq_ids:
            return
        await self._session.execute(
            text(
                """
                INSERT INTO public.pl_post_faqs (post_id, faq_id, position)
                SELECT :post_id, faq_id, ord - 1
                FROM UNNEST(CAST(:faq_ids AS BIGINT[])) WITH ORDINALITY AS t(faq_id, ord)
                """
            ),
            {"post_id": post_id, "faq_ids": faq_ids},
        )

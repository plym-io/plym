from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from plym.exceptions.categories import CategoryConflictError
from plym.instrumentation.tracer import Traced

_COLUMNS = "id, name, slug, weight"


class CategoryRepository(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, name: str, slug: str, weight: int | None) -> dict[str, Any]:
        try:
            result = await self._session.execute(
                text(
                    f"""
                    INSERT INTO public.pl_categories (name, slug, weight)
                    VALUES (:name, :slug, :weight)
                    RETURNING {_COLUMNS}
                    """
                ),
                {"name": name, "slug": slug, "weight": weight},
            )
        except IntegrityError as e:
            raise CategoryConflictError(name) from e
        return dict(result.mappings().one())

    async def list_all(self) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text(
                f"SELECT {_COLUMNS} FROM public.pl_categories ORDER BY weight ASC NULLS LAST, name"
            )
        )
        return [dict(r) for r in result.mappings().all()]

    async def get_by_id(self, category_id: int) -> dict[str, Any] | None:
        result = await self._session.execute(
            text(f"SELECT {_COLUMNS} FROM public.pl_categories WHERE id = :id"),
            {"id": category_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def slug_exists(self, slug: str) -> bool:
        result = await self._session.execute(
            text("SELECT 1 FROM public.pl_categories WHERE slug = :slug LIMIT 1"),
            {"slug": slug},
        )
        return result.first() is not None

    async def conflicts(self, *, name: str, slug: str, exclude_id: int | None = None) -> bool:
        scope = "AND id <> :exclude_id" if exclude_id is not None else ""
        params: dict[str, Any] = {"name": name, "slug": slug}
        if exclude_id is not None:
            params["exclude_id"] = exclude_id
        result = await self._session.execute(
            text(
                f"""
                SELECT 1 FROM public.pl_categories
                WHERE (name = :name OR slug = :slug) {scope}
                LIMIT 1
                """
            ),
            params,
        )
        return result.first() is not None

    _UPDATABLE_FIELDS = {"name", "slug", "weight"}

    async def update_fields(
        self, category_id: int, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        assignable = {k: v for k, v in fields.items() if k in self._UPDATABLE_FIELDS}
        if not assignable:
            return await self.get_by_id(category_id)
        set_clause = ", ".join(f"{k} = :{k}" for k in assignable)
        try:
            result = await self._session.execute(
                text(
                    f"""
                    UPDATE public.pl_categories SET {set_clause} WHERE id = :id
                    RETURNING {_COLUMNS}
                    """
                ),
                {**assignable, "id": category_id},
            )
        except IntegrityError as e:
            raise CategoryConflictError(str(assignable.get("name") or category_id)) from e
        row = result.mappings().first()
        return dict(row) if row else None

    async def delete(self, category_id: int) -> bool:
        result = await self._session.execute(
            text("DELETE FROM public.pl_categories WHERE id = :id RETURNING id"),
            {"id": category_id},
        )
        return result.first() is not None

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plym.instrumentation.tracer import Traced


class MediaRepository(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(
        self,
        *,
        filename: str,
        original_name: str | None,
        mime_type: str,
        size_bytes: int,
        width: int | None,
        height: int | None,
        url: str,
        uploader_id: int,
    ) -> dict:
        result = await self._session.execute(
            text(
                """
                INSERT INTO public.pl_media
                    (filename, original_name, mime_type, size_bytes, width, height, url, uploader_id)
                VALUES (:filename, :original_name, :mime_type, :size_bytes, :width, :height, :url, :uploader_id)
                RETURNING id, filename, original_name, mime_type, size_bytes, width, height,
                          url, uploader_id, created_at
                """
            ),
            {
                "filename": filename,
                "original_name": original_name,
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "width": width,
                "height": height,
                "url": url,
                "uploader_id": uploader_id,
            },
        )
        return dict(result.mappings().one())

    async def get_by_id(self, media_id: int) -> dict | None:
        result = await self._session.execute(
            text(
                """
                SELECT id, filename, original_name, mime_type, size_bytes, width, height,
                       url, uploader_id, created_at
                FROM public.pl_media
                WHERE id = :id
                """
            ),
            {"id": media_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def list_paginated(self, *, limit: int, offset: int) -> list[dict]:
        result = await self._session.execute(
            text(
                """
                SELECT id, filename, original_name, mime_type, size_bytes, width, height,
                       url, uploader_id, created_at
                FROM public.pl_media
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        )
        return [dict(r) for r in result.mappings().all()]

    async def count(self) -> int:
        result = await self._session.execute(text("SELECT COUNT(*) FROM public.pl_media"))
        return int(result.scalar_one())

    async def delete(self, media_id: int) -> None:
        await self._session.execute(
            text("DELETE FROM public.pl_media WHERE id = :id"),
            {"id": media_id},
        )

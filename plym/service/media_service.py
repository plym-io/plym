import io
import uuid

import aiofiles
from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from plym.config.site import SiteConfig
from plym.exceptions.media import (
    MediaForbiddenError,
    MediaInUseError,
    MediaNotFoundError,
    UnsupportedImageError,
    UploadTooLargeError,
)
from plym.instrumentation.decorators import instrumented
from plym.models.media import MediaItem
from plym.repository.media_repository import MediaRepository
from plym.repository.post_repository import PostRepository
from plym.settings import settings


class MediaService:
    def __init__(self, session: AsyncSession, site: SiteConfig) -> None:
        self._session = session
        self._site = site
        self._media = MediaRepository(session)
        self._posts = PostRepository(session)

    def _public_url(self, filename: str) -> str:
        base = self._site.media.location.rstrip("/") if self._site.media.location else "/media"
        return f"{base}/{filename}"

    @instrumented("media.upload", audit=True)
    async def upload(self, *, uploader_id: int, original_name: str, data: bytes) -> MediaItem:
        if len(data) > settings.upload_max_bytes:
            raise UploadTooLargeError(settings.upload_max_bytes)
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except (UnidentifiedImageError, OSError) as e:
            raise UnsupportedImageError() from e

        width, height = image.size
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
        else:
            image = image.convert("RGB")

        filename = f"{uuid.uuid4().hex}.webp"
        buf = io.BytesIO()
        image.save(buf, format="WEBP", quality=82, method=6)
        webp_bytes = buf.getvalue()

        target_path = settings.uploads_dir / filename
        async with aiofiles.open(target_path, "wb") as f:
            await f.write(webp_bytes)

        row = await self._media.insert(
            filename=filename,
            original_name=original_name,
            mime_type="image/webp",
            size_bytes=len(webp_bytes),
            width=width,
            height=height,
            url=self._public_url(filename),
            uploader_id=uploader_id,
        )
        await self._session.commit()
        return MediaItem.model_validate(row)

    async def list_paginated(self, *, page: int, page_size: int) -> tuple[list[MediaItem], int]:
        offset = max(0, (page - 1) * page_size)
        rows = await self._media.list_paginated(limit=page_size, offset=offset)
        total = await self._media.count()
        return [MediaItem.model_validate(r) for r in rows], total

    async def get(self, media_id: int) -> MediaItem:
        row = await self._media.get_by_id(media_id)
        if not row:
            raise MediaNotFoundError()
        return MediaItem.model_validate(row)

    @instrumented("media.delete", audit=True)
    async def delete(self, *, media_id: int, requester_id: int) -> None:
        row = await self._media.get_by_id(media_id)
        if not row:
            raise MediaNotFoundError()
        if row["uploader_id"] != requester_id:
            raise MediaForbiddenError()

        references = await self._posts.find_references_to_filename(row["filename"])
        if references:
            raise MediaInUseError(references)

        file_path = settings.uploads_dir / row["filename"]
        if file_path.exists():
            file_path.unlink()
        await self._media.delete(media_id)
        await self._session.commit()

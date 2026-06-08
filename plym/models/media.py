from datetime import datetime

from plym.models.common import ORMModel


class MediaItem(ORMModel):
    id: int
    filename: str
    original_name: str | None
    mime_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    url: str
    uploader_id: int | None = None
    created_at: datetime


class MediaReference(ORMModel):
    id: int
    slug: str
    title: str

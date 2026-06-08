from datetime import datetime

from pydantic import BaseModel, Field

from plym.models.common import ORMModel, PostStatus, Timestamped
from plym.models.tag import Tag
from plym.models.user import UserPublic

_URL_PATTERN = r"^https?://.+"


class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    slug: str = Field(min_length=1, max_length=240, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    content: str = ""
    excerpt: str | None = None
    cover: str | None = None
    canonical_url: str | None = Field(default=None, max_length=2048, pattern=_URL_PATTERN)
    tags: list[str] = Field(default_factory=list)


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    content: str | None = None
    excerpt: str | None = None
    cover: str | None = None
    canonical_url: str | None = Field(default=None, max_length=2048, pattern=_URL_PATTERN)
    status: PostStatus | None = None
    tags: list[str] | None = None


class PostListItem(Timestamped):
    id: int
    slug: str
    title: str
    status: PostStatus
    reading_time: int
    excerpt: str | None = None
    cover: str | None = None
    canonical_url: str | None = None
    published_at: datetime | None = None
    author: UserPublic
    tags: list[Tag] = Field(default_factory=list)


class Post(PostListItem):
    content: str
    rendered_path: str | None = None


class PreviewRequest(BaseModel):
    title: str
    content: str
    excerpt: str | None = None
    cover: str | None = None
    canonical_url: str | None = Field(default=None, max_length=2048, pattern=_URL_PATTERN)


class PreviewResponse(BaseModel):
    html: str

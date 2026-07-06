from datetime import datetime

from pydantic import BaseModel, Field


class SearchDocument(BaseModel):
    id: int
    slug: str
    url: str
    title: str
    excerpt: str | None = None
    tags: list[str] = Field(default_factory=list)
    author: str
    reading_time: int
    published_at: datetime | None = None
    updated_at: datetime | None = None
    text: str


class SearchIndex(BaseModel):
    version: int = 1
    generated_at: datetime
    site: str
    base_url: str
    count: int
    documents: list[SearchDocument]


class SearchIndexBuildResult(BaseModel):
    documents: int
    generated_at: datetime

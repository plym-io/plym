from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiofiles
from sqlalchemy.ext.asyncio import AsyncSession

from plym.config.site import SiteConfig
from plym.instrumentation.tracer import Traced
from plym.models.search_index import SearchDocument, SearchIndex
from plym.render.excerpt import resolve_excerpt
from plym.render.markdown_renderer import MarkdownRenderer
from plym.render.plain_text import extract_text
from plym.render.urls import path_for_row
from plym.repository.post_repository import PostRepository
from plym.settings import settings

_BATCH_SIZE = 200


def index_path() -> Path:
    return settings.generated_dir / "index.json"


class SearchIndexService(Traced):
    def __init__(self, session: AsyncSession, site: SiteConfig) -> None:
        self._posts = PostRepository(session)
        self._site = site
        self._markdown = MarkdownRenderer()

    async def build(self) -> SearchIndex:
        base = self._site.public_blog_url()
        documents: list[SearchDocument] = []
        after = 0
        while True:
            rows = await self._posts.list_published_for_index_after(after=after, limit=_BATCH_SIZE)
            if not rows:
                break
            documents.extend(self._to_document(row, base) for row in rows)
            after = rows[-1]["id"]
            if len(rows) < _BATCH_SIZE:
                break
        index = SearchIndex(
            generated_at=datetime.now(UTC),
            site=self._site.name,
            base_url=base,
            count=len(documents),
            documents=documents,
        )
        await self._write(index)
        return index

    async def refresh(self) -> SearchIndex | None:
        if not index_path().exists():
            return None
        return await self.build()

    def _to_document(self, row: dict[str, Any], base: str) -> SearchDocument:
        html, _ = self._markdown.render(row["content"])
        return SearchDocument(
            id=row["id"],
            slug=row["slug"],
            url=f"{base}/{path_for_row(row)}",
            title=row["title"],
            excerpt=resolve_excerpt(row.get("excerpt"), row["content"]),
            category=row.get("category_slug"),
            tags=[tag["name"] for tag in row["tags"]],
            author=row["display_name"],
            reading_time=row["reading_time"],
            published_at=row.get("published_at"),
            updated_at=row.get("updated_at"),
            text=extract_text(html),
        )

    async def _write(self, index: SearchIndex) -> None:
        target = index_path()
        tmp = target.with_suffix(".json.tmp")
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write(index.model_dump_json())
        tmp.replace(target)

    @staticmethod
    def read() -> str | None:
        target = index_path()
        if not target.exists():
            return None
        return target.read_text(encoding="utf-8")

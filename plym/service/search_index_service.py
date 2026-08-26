import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from plym.config.site import SiteConfig
from plym.instrumentation.tracer import Traced
from plym.models.search_index import SearchDocument, SearchIndex
from plym.render.excerpt import resolve_excerpt
from plym.render.urls import path_for_row
from plym.repository.post_repository import PostRepository
from plym.service.artifact_writer import write_if_changed
from plym.settings import settings

_BATCH_SIZE = 200
_TIMESTAMP_FIELD = "generated_at"


def index_path() -> Path:
    return settings.generated_dir / "index.json"


def _on_disk(target: Path) -> dict[str, Any] | None:
    if not target.exists():
        return None
    try:
        parsed: Any = json.loads(target.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return cast(dict[str, Any], parsed)


def _content(index: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in index.items() if key != _TIMESTAMP_FIELD}


def _timestamp_if_unchanged(target: Path, candidate: dict[str, Any]) -> datetime | None:
    """The artifact's own generated_at, when its content already matches the candidate.

    Whatever watches .generated/ purges what it sees change, and generated_at moves on
    every build, so comparing whole bodies would fan out a purge for an index that did
    not move.
    """
    previous = _on_disk(target)
    if previous is None or _content(previous) != _content(candidate):
        return None
    written = previous.get(_TIMESTAMP_FIELD)
    if not isinstance(written, str):
        return None
    try:
        return datetime.fromisoformat(written)
    except ValueError:
        return None


class SearchIndexService(Traced):
    def __init__(self, session: AsyncSession, site: SiteConfig) -> None:
        self._posts = PostRepository(session)
        self._site = site

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
        return await self._write(index)

    async def refresh(self) -> SearchIndex | None:
        if not index_path().exists():
            return None
        return await self.build()

    @staticmethod
    def _to_document(row: dict[str, Any], base: str) -> SearchDocument:
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
        )

    async def _write(self, index: SearchIndex) -> SearchIndex:
        target = index_path()
        body = index.model_dump_json()
        unchanged = _timestamp_if_unchanged(target, json.loads(body))
        if unchanged is not None:
            return index.model_copy(update={_TIMESTAMP_FIELD: unchanged})
        await write_if_changed(target, body)
        return index

    @staticmethod
    def read() -> str | None:
        target = index_path()
        if not target.exists():
            return None
        return target.read_text(encoding="utf-8")

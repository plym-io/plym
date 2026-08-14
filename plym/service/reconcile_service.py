import logging
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from plym.config.site import SiteConfig
from plym.db.session import get_session_factory
from plym.instrumentation.tracer import Traced
from plym.models.refresh import RefreshReport
from plym.render.stamp import read_render_stamp
from plym.render.urls import is_index_path, path_for_row
from plym.repository.post_repository import PostRepository
from plym.service.post_pipeline import PostPipeline
from plym.service.site_files_service import refresh_site_artifacts
from plym.settings import settings

log = logging.getLogger("plym.reconcile")

_SLUG_CHUNK = 1000
_RENDER_CHUNK = 200


class ReconcileService(Traced):
    def __init__(self, session: AsyncSession, site: SiteConfig, pipeline: PostPipeline) -> None:
        self._session = session
        self._site = site
        self._pipeline = pipeline
        self._posts = PostRepository(session)

    async def run(self, *, force: bool = False) -> RefreshReport:
        _remove_tmp_files()
        published = await self._published_paths()
        removed = _remove_orphans(published)
        stale = published if force else _stale_paths(published, self._pipeline.render_stamp)
        rendered = await self._rerender(stale)
        await refresh_site_artifacts(self._session, self._site, self._pipeline)
        return RefreshReport(
            published=len(published),
            stale=len(stale),
            rendered=rendered,
            failed=len(stale) - rendered,
            removed=removed,
        )

    async def _published_paths(self) -> set[str]:
        paths: set[str] = set()
        after = 0
        while True:
            chunk = await self._posts.list_published_slugs_after(after=after, limit=_SLUG_CHUNK)
            if not chunk:
                return paths
            paths.update(path_for_row(row) for row in chunk)
            after = chunk[-1]["id"]
            if len(chunk) < _SLUG_CHUNK:
                return paths

    async def _rerender(self, stale: set[str]) -> int:
        if not stale:
            return 0
        rendered = 0
        after = 0
        while True:
            chunk = await self._posts.list_published_full_after(after=after, limit=_RENDER_CHUNK)
            if not chunk:
                return rendered
            for row in chunk:
                if path_for_row(row) in stale and await self._rerender_one(row):
                    rendered += 1
            after = chunk[-1]["id"]
            if len(chunk) < _RENDER_CHUNK:
                return rendered

    async def _rerender_one(self, row: dict[str, Any]) -> bool:
        try:
            await self._pipeline.render_row(row)
            return True
        except Exception:
            log.exception("failed to re-render %s", row["slug"])
            return False


async def reconcile_generated_files(pipeline: PostPipeline, site: SiteConfig) -> None:
    factory = get_session_factory()
    try:
        async with factory() as session:
            report = await ReconcileService(session, site, pipeline).run()
    except Exception:
        log.exception("startup reconcile of .generated/ failed")
        return
    if report.removed:
        log.warning("reconciled .generated/: removed %d orphan file(s)", report.removed)
    if not report.stale:
        return
    if report.failed:
        log.error(
            "re-rendered %d/%d stale post(s) — inspect failures above",
            report.rendered,
            report.stale,
        )
    else:
        log.warning("re-rendered %d stale post(s)", report.rendered)


def _remove_tmp_files() -> None:
    for path in settings.generated_dir.rglob("*.tmp"):
        path.unlink()


def _relative_path(path: Path) -> str:
    return path.relative_to(settings.generated_dir).with_suffix("").as_posix()


def _remove_orphans(published: set[str]) -> int:
    removed = 0
    for pattern in ("*.html", "*.md"):
        for path in settings.generated_dir.rglob(pattern):
            relative = _relative_path(path)
            # The index pages are artifacts too, and no post owns them; IndexArtifactService
            # prunes the ones that outlive their page count.
            if is_index_path(relative) or relative in published:
                continue
            path.unlink()
            removed += 1
    _prune_empty_dirs()
    return removed


def _prune_empty_dirs() -> None:
    for path in sorted(settings.generated_dir.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def _stale_paths(published: set[str], current_stamp: str) -> set[str]:
    stale: set[str] = set()
    for relative in published:
        path = settings.generated_dir / f"{relative}.html"
        markdown = settings.generated_dir / f"{relative}.md"
        if (
            not path.exists()
            or not markdown.exists()
            or read_render_stamp(path.read_text(encoding="utf-8")) != current_stamp
        ):
            stale.add(relative)
    return stale

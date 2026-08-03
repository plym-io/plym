import logging
from pathlib import Path
from typing import Any

from plym.db.session import get_session_factory
from plym.render.stamp import read_render_stamp
from plym.render.urls import path_for_row
from plym.repository.post_repository import PostRepository
from plym.service.post_pipeline import PostPipeline
from plym.settings import settings

log = logging.getLogger("plym.reconcile")


async def reconcile_generated_files(pipeline: PostPipeline) -> None:
    if not settings.generated_dir.exists():
        return
    _remove_tmp_files()
    try:
        published = await _published_paths()
    except Exception as exc:
        log.warning("reconcile skipped — could not read published slugs: %s", exc)
        return

    removed = _remove_orphans(published)
    if removed:
        log.warning("reconciled .generated/: removed %d orphan file(s)", removed)

    stale = _stale_paths(published, pipeline.render_stamp)
    if not stale:
        return
    log.warning("reconciled .generated/: %d stale or missing file(s), re-rendering", len(stale))
    try:
        rendered = await _rerender(pipeline, stale)
    except Exception:
        log.exception("re-render sweep failed")
        return
    if rendered < len(stale):
        log.error("re-rendered %d/%d stale post(s) — inspect failures above", rendered, len(stale))
    else:
        log.warning("re-rendered %d stale post(s)", rendered)


def _remove_tmp_files() -> None:
    for pattern in ("*.html.tmp", "*.md.tmp"):
        for path in settings.generated_dir.rglob(pattern):
            path.unlink()


async def _published_paths() -> set[str]:
    paths: set[str] = set()
    factory = get_session_factory()
    async with factory() as session:
        posts = PostRepository(session)
        after = 0
        while True:
            chunk = await posts.list_published_slugs_after(after=after, limit=1000)
            if not chunk:
                break
            paths.update(path_for_row(row) for row in chunk)
            after = chunk[-1]["id"]
            if len(chunk) < 1000:
                break
    return paths


def _relative_path(path: Path) -> str:
    return path.relative_to(settings.generated_dir).with_suffix("").as_posix()


def _remove_orphans(published: set[str]) -> int:
    removed = 0
    for pattern in ("*.html", "*.md"):
        for path in settings.generated_dir.rglob(pattern):
            if _relative_path(path) not in published:
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


async def _rerender(pipeline: PostPipeline, stale: set[str]) -> int:
    rendered = 0
    factory = get_session_factory()
    async with factory() as session:
        posts = PostRepository(session)
        after = 0
        while True:
            chunk = await posts.list_published_full_after(after=after, limit=200)
            if not chunk:
                break
            for row in chunk:
                if path_for_row(row) in stale and await _rerender_one(pipeline, row):
                    rendered += 1
            after = chunk[-1]["id"]
            if len(chunk) < 200:
                break
    return rendered


async def _rerender_one(pipeline: PostPipeline, row: dict[str, Any]) -> bool:
    try:
        await pipeline.render_row(row)
        return True
    except Exception:
        log.exception("failed to re-render %s", row["slug"])
        return False

import logging

from plym.db.session import get_session_factory
from plym.render.stamp import read_render_stamp
from plym.repository.post_repository import PostRepository
from plym.service.post_pipeline import PostPipeline
from plym.settings import settings

log = logging.getLogger("plym.reconcile")


async def reconcile_generated_files(pipeline: PostPipeline) -> None:
    if not settings.generated_dir.exists():
        return
    _remove_tmp_files()
    try:
        published = await _published_slugs()
    except Exception as exc:
        log.warning("reconcile skipped — could not read published slugs: %s", exc)
        return

    removed = _remove_orphans(published)
    if removed:
        log.warning("reconciled .generated/: removed %d orphan file(s)", removed)

    stale = _stale_slugs(published, pipeline.render_stamp)
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
        for path in settings.generated_dir.glob(pattern):
            path.unlink()


async def _published_slugs() -> set[str]:
    slugs: set[str] = set()
    factory = get_session_factory()
    async with factory() as session:
        posts = PostRepository(session)
        after = 0
        while True:
            chunk = await posts.list_published_slugs_after(after=after, limit=1000)
            if not chunk:
                break
            slugs.update(row["slug"] for row in chunk)
            after = chunk[-1]["id"]
            if len(chunk) < 1000:
                break
    return slugs


def _remove_orphans(published: set[str]) -> int:
    removed = 0
    for pattern in ("*.html", "*.md"):
        for path in settings.generated_dir.glob(pattern):
            if path.stem not in published:
                path.unlink()
                removed += 1
    return removed


def _stale_slugs(published: set[str], current_stamp: str) -> set[str]:
    stale: set[str] = set()
    for slug in published:
        path = settings.generated_dir / f"{slug}.html"
        if (
            not path.exists()
            or read_render_stamp(path.read_text(encoding="utf-8")) != current_stamp
        ):
            stale.add(slug)
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
                if row["slug"] in stale and await _rerender_one(pipeline, row):
                    rendered += 1
            after = chunk[-1]["id"]
            if len(chunk) < 200:
                break
    return rendered


async def _rerender_one(pipeline: PostPipeline, row: dict) -> bool:
    try:
        await pipeline.render_and_persist(
            slug=row["slug"],
            title=row["title"],
            content=row["content"],
            excerpt=row.get("excerpt"),
            cover=row.get("cover"),
            canonical_url=row.get("canonical_url"),
            author={
                "display_name": row["display_name"],
                "avatar_url": row.get("avatar_url"),
                "links": row.get("links") or [],
            },
            published_at=row.get("published_at"),
            updated_at=row.get("updated_at"),
            tags=row["tags"],
            faqs=row["faqs"],
        )
        return True
    except Exception:
        log.exception("failed to re-render %s", row["slug"])
        return False

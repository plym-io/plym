import logging

from sqlalchemy import text

from plym.db.session import get_session_factory
from plym.settings import settings

log = logging.getLogger("plym.reconcile")


async def reconcile_generated_files() -> int:
    if not settings.generated_dir.exists():
        return 0
    try:
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                text("SELECT slug FROM public.pl_posts WHERE status = 'published'")
            )
            published_slugs = {row[0] for row in result}
    except Exception as exc:
        log.warning("reconcile skipped — could not read published slugs: %s", exc)
        return 0

    removed = 0
    for path in settings.generated_dir.glob("*.html"):
        if path.stem not in published_slugs:
            path.unlink()
            removed += 1

    if removed:
        log.warning("reconciled .generated/: removed %d orphan file(s)", removed)
    return removed

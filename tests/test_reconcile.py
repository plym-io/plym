import uuid

import pytest
from sqlalchemy import text

from tests.conftest import TEST_MODE

pytestmark = pytest.mark.skipif(
    TEST_MODE != "inprocess", reason="reconcile runs against the database directly"
)


@pytest.mark.asyncio
async def test_reconcile_rerenders_stale_and_missing_files() -> None:
    from plym.db.session import dispose_engine, get_session_factory
    from plym.main import app
    from plym.render.stamp import read_render_stamp
    from plym.service.post_pipeline import PostPipeline
    from plym.service.reconcile_service import reconcile_generated_files
    from plym.settings import settings

    stale_slug = f"test-reconcile-stale-{uuid.uuid4().hex[:12]}"
    missing_slug = f"test-reconcile-missing-{uuid.uuid4().hex[:12]}"
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("SELECT id FROM public.pl_users ORDER BY id LIMIT 1")
        )
        author_id = result.scalar_one()
        for slug in (stale_slug, missing_slug):
            await session.execute(
                text(
                    """
                    INSERT INTO public.pl_posts
                        (slug, title, author_id, content, status, reading_time, published_at)
                    VALUES (:slug, :title, :author_id, '# hi', 'published', 1, NOW())
                    """
                ),
                {"slug": slug, "title": slug, "author_id": author_id},
            )
        await session.commit()

    stale_file = settings.generated_dir / f"{stale_slug}.html"
    stale_file.write_text(
        "<!DOCTYPE html><html><head></head><body>stale</body></html>", encoding="utf-8"
    )
    pipeline = PostPipeline(app.state.site, app.state.css, app.state.prism_js)
    try:
        await reconcile_generated_files(pipeline)
        for slug in (stale_slug, missing_slug):
            html = (settings.generated_dir / f"{slug}.html").read_text(encoding="utf-8")
            assert read_render_stamp(html) == pipeline.render_stamp
            assert '"@type": "BlogPosting"' in html
    finally:
        async with factory() as session:
            await session.execute(
                text("DELETE FROM public.pl_posts WHERE slug IN (:a, :b)"),
                {"a": stale_slug, "b": missing_slug},
            )
            await session.commit()
        for slug in (stale_slug, missing_slug):
            for suffix in (".html", ".md"):
                path = settings.generated_dir / f"{slug}{suffix}"
                if path.exists():
                    path.unlink()
        await dispose_engine()


@pytest.mark.asyncio
async def test_reconcile_skips_current_files() -> None:
    from plym.db.session import dispose_engine, get_session_factory
    from plym.main import app
    from plym.service.post_pipeline import PostPipeline
    from plym.service.reconcile_service import reconcile_generated_files
    from plym.settings import settings

    slug = f"test-reconcile-current-{uuid.uuid4().hex[:12]}"
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("SELECT id FROM public.pl_users ORDER BY id LIMIT 1")
        )
        author_id = result.scalar_one()
        await session.execute(
            text(
                """
                INSERT INTO public.pl_posts
                    (slug, title, author_id, content, status, reading_time, published_at)
                VALUES (:slug, :title, :author_id, '# hi', 'published', 1, NOW())
                """
            ),
            {"slug": slug, "title": slug, "author_id": author_id},
        )
        await session.commit()

    pipeline = PostPipeline(app.state.site, app.state.css, app.state.prism_js)
    target = settings.generated_dir / f"{slug}.html"
    try:
        await reconcile_generated_files(pipeline)
        marker = target.read_text(encoding="utf-8") + "<!-- untouched -->"
        target.write_text(marker, encoding="utf-8")
        await reconcile_generated_files(pipeline)
        assert target.read_text(encoding="utf-8") == marker
    finally:
        async with factory() as session:
            await session.execute(
                text("DELETE FROM public.pl_posts WHERE slug = :slug"), {"slug": slug}
            )
            await session.commit()
        for suffix in (".html", ".md"):
            path = settings.generated_dir / f"{slug}{suffix}"
            if path.exists():
                path.unlink()
        await dispose_engine()

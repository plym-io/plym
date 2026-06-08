from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from plym.api.auth_router import router as auth_router
from plym.api.blog_router import index_router, posts_router as blog_posts_router
from plym.api.config_router import router as config_router
from plym.api.logs_router import router as logs_router
from plym.api.media_router import router as media_router
from plym.api.posts_router import router as posts_router
from plym.api.seo_router import router as seo_router
from plym.api.tags_router import router as tags_router
from plym.api.users_router import router as users_router
from plym.build.pipeline import run_build
from plym.config.site import load_site_config
from plym.db.migrate import apply_migrations
from plym.db.session import dispose_engine
from plym.instrumentation.middleware import ActorMiddleware
from plym.render.reconcile import reconcile_generated_files
from plym.service.backup_service import BackupScheduler
from plym.service.bootstrap import ensure_superuser
from plym.service.token_service import TokenService
from plym.settings import settings


def _ensure_storage_dirs() -> None:
    for path in (
        settings.storage_dir,
        settings.uploads_dir,
        settings.generated_dir,
        settings.backups_dir,
        settings.fonts_dir,
        settings.static_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


_ensure_storage_dirs()
_site_config = load_site_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    site = load_site_config()
    await apply_migrations()
    await ensure_superuser()
    await reconcile_generated_files()
    artifacts = await run_build(site)

    app.state.site = site
    app.state.settings = settings
    app.state.css = artifacts.css
    app.state.prism_js = artifacts.prism_js

    scheduler = BackupScheduler(site.backup.frequency)
    scheduler.start()
    app.state.backup_scheduler = scheduler

    yield

    await scheduler.stop()
    await dispose_engine()


app = FastAPI(title="Plym", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(ActorMiddleware, jwt=TokenService())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(posts_router)
app.include_router(media_router)
app.include_router(tags_router)
app.include_router(config_router)
app.include_router(logs_router)
app.include_router(seo_router)
app.include_router(index_router)
app.include_router(blog_posts_router, prefix=_site_config.blog_prefix)

app.mount("/webfonts", StaticFiles(directory=settings.fonts_dir), name="webfonts")
if not _site_config.media.location:
    app.mount("/media", StaticFiles(directory=settings.uploads_dir), name="media")

_admin_dir = Path("/app/admin")
if _admin_dir.is_dir() and (_admin_dir / "index.html").exists():
    app.mount("/admin", StaticFiles(directory=str(_admin_dir), html=True), name="admin")

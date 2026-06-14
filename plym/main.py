import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from plym.api.auth_router import router as auth_router
from plym.api.blog_router import index_router, serve_index
from plym.api.blog_router import posts_router as blog_posts_router
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
from plym.instrumentation.log_config import configure_logging
from plym.instrumentation.middleware import ActorMiddleware
from plym.render.reconcile import reconcile_generated_files
from plym.service.backup_service import BackupScheduler
from plym.service.bootstrap import ensure_superuser
from plym.service.token_service import TokenService
from plym.settings import settings

configure_logging()
log = logging.getLogger("plym.startup")


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
    log.info("startup: applying migrations")
    await apply_migrations()
    log.info("startup: ensuring superuser")
    await ensure_superuser()
    log.info("startup: reconciling generated files")
    await reconcile_generated_files()
    log.info("startup: running build (fonts, prism, assets, css)")
    artifacts = await run_build(site)
    if artifacts.assets.favicon is not None:
        site.favicon = artifacts.assets.favicon.web_path
    if artifacts.assets.logo is not None:
        site.logo = artifacts.assets.logo.web_path

    app.state.site = site
    app.state.settings = settings
    app.state.css = artifacts.css
    app.state.prism_js = artifacts.prism_js

    scheduler = BackupScheduler(site.backup.frequency)
    scheduler.start()
    app.state.backup_scheduler = scheduler

    log.info("startup: complete — now serving")
    yield

    log.info("shutdown: stopping scheduler and disposing engine")
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

class AdminSPA(StaticFiles):
    def __init__(self, directory: str, base_href: str) -> None:
        super().__init__(directory=directory)
        index = Path(directory) / "index.html"
        self._index = index.read_text(encoding="utf-8").replace(
            "<head>", f'<head><base href="{base_href}/">', 1
        )

    async def get_response(self, path: str, scope):
        if path not in ("", ".", "index.html"):
            try:
                response = await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code != 404:
                    raise
            else:
                if response.status_code != 404:
                    return response
        return HTMLResponse(self._index)


_prefix = _site_config.blog_prefix
_admin_dir = Path("/app/admin")
_admin_available = _admin_dir.is_dir() and (_admin_dir / "index.html").exists()

if _prefix:
    app.include_router(seo_router, prefix=_prefix, include_in_schema=False)
    app.add_api_route(_prefix, serve_index, response_class=HTMLResponse, include_in_schema=False)
    app.add_api_route(
        f"{_prefix}/", serve_index, response_class=HTMLResponse, include_in_schema=False
    )
    app.mount(
        f"{_prefix}/webfonts", StaticFiles(directory=settings.fonts_dir), name="blog-webfonts"
    )
    if not _site_config.media.location:
        app.mount(
            f"{_prefix}/media", StaticFiles(directory=settings.uploads_dir), name="blog-media"
        )

if _admin_available:
    async def _admin_redirect() -> RedirectResponse:
        return RedirectResponse(f"{_prefix}/plym-admin/")

    app.add_api_route(f"{_prefix}/plym-admin", _admin_redirect, include_in_schema=False)
    app.mount(
        f"{_prefix}/plym-admin",
        AdminSPA(str(_admin_dir), f"{_prefix}/plym-admin"),
        name="blog-admin",
    )

app.include_router(blog_posts_router, prefix=_site_config.blog_prefix)

app.mount("/webfonts", StaticFiles(directory=settings.fonts_dir), name="webfonts")
if not _site_config.media.location:
    app.mount("/media", StaticFiles(directory=settings.uploads_dir), name="media")

if _admin_available:
    app.mount("/admin", AdminSPA(str(_admin_dir), "/admin"), name="admin")

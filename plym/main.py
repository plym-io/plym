import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response
from starlette.types import Scope

from plym.api.auth_router import router as auth_router
from plym.api.blog_router import index_router
from plym.api.blog_router import posts_router as blog_posts_router
from plym.api.categories_router import router as categories_router
from plym.api.config_router import router as config_router
from plym.api.faqs_router import router as faqs_router
from plym.api.media_router import router as media_router
from plym.api.openapi_router import router as openapi_router
from plym.api.posts_router import router as posts_router
from plym.api.search_router import api_router as search_api_router
from plym.api.search_router import index_json_router
from plym.api.seo_router import router as seo_router
from plym.api.submissions_router import router as submissions_router
from plym.api.tags_router import router as tags_router
from plym.api.users_router import router as users_router
from plym.build.pipeline import run_build
from plym.config.site import load_site_config
from plym.db.migrate import apply_migrations
from plym.db.session import dispose_engine
from plym.instrumentation.middleware import ActorMiddleware
from plym.instrumentation.redirects import CanonicalRedirectMiddleware
from plym.instrumentation.telemetry import configure_telemetry
from plym.render.cache_policy import REDIRECT_CACHE_CONTROL
from plym.service.backup_service import BackupScheduler
from plym.service.bootstrap import ensure_superuser
from plym.service.post_pipeline import PostPipeline
from plym.service.reconcile_service import reconcile_generated_files
from plym.service.token_service import TokenService
from plym.settings import settings

configure_telemetry()
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
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    site = load_site_config()
    log.info("startup: applying migrations")
    await apply_migrations()
    log.info("startup: ensuring superuser")
    await ensure_superuser()
    log.info("startup: running build (fonts, prism, assets, css)")
    artifacts = await run_build(site)
    if artifacts.assets.favicon is not None:
        site.favicon = artifacts.assets.favicon.web_path
    if artifacts.assets.logo is not None:
        site.logo = artifacts.assets.logo.web_path

    log.info("startup: reconciling generated files")
    await reconcile_generated_files(PostPipeline(site, artifacts.css, artifacts.prism_js), site)

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


docs: dict[str, Any] = {
    "docs_url": None,
    "redoc_url": None,
    "openapi_url": None,
}
if settings.debug:
    docs = {
        "docs_url": "/plym-docs",
        "redoc_url": None,
        "openapi_url": "/plym-docs/openapi.json",
    }
app = FastAPI(
    title="Plym",
    lifespan=lifespan,
    **docs,
)
FastAPIInstrumentor.instrument_app(app)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(ActorMiddleware, jwt=TokenService())
app.add_middleware(CanonicalRedirectMiddleware)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(posts_router)
app.include_router(media_router)
app.include_router(tags_router)
app.include_router(categories_router)
app.include_router(faqs_router)
app.include_router(config_router)
app.include_router(openapi_router)
app.include_router(submissions_router)
app.include_router(search_api_router)
app.include_router(seo_router)
app.include_router(index_json_router)


def _canonical_redirect(location: str) -> RedirectResponse:
    return RedirectResponse(
        location, status_code=308, headers={"Cache-Control": REDIRECT_CACHE_CONTROL}
    )


SHELL_CACHE_CONTROL = "no-store"
HASHED_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
UNHASHED_ASSET_CACHE_CONTROL = "no-cache"

_HASHED_ASSET_DIR = "assets/"
_HASHED_ASSET_NAME = re.compile(r"-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$")


def admin_cache_control(path: str) -> str:
    relative = path.lstrip("/")
    if relative.startswith(_HASHED_ASSET_DIR) and _HASHED_ASSET_NAME.search(relative):
        return HASHED_ASSET_CACHE_CONTROL
    return UNHASHED_ASSET_CACHE_CONTROL


class AdminSPA(StaticFiles):
    def __init__(self, directory: str, base_href: str) -> None:
        super().__init__(directory=directory)
        index = Path(directory) / "index.html"
        self._index = index.read_text(encoding="utf-8").replace(
            "<head>", f'<head><base href="{base_href}/">', 1
        )

    async def get_response(self, path: str, scope: Scope) -> Response:
        if path not in ("", ".", "index.html"):
            try:
                response = await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code != 404:
                    raise
            else:
                if response.status_code != 404:
                    response.headers["Cache-Control"] = admin_cache_control(path)
                    return response
        shell = HTMLResponse(self._index)
        shell.headers["Cache-Control"] = SHELL_CACHE_CONTROL
        return shell


_prefix = _site_config.blog_prefix
_admin_dir = Path("/app/admin")
_admin_available = _admin_dir.is_dir() and (_admin_dir / "index.html").exists()

if _prefix:
    app.include_router(seo_router, prefix=_prefix, include_in_schema=False)
    app.include_router(index_json_router, prefix=_prefix, include_in_schema=False)

    async def _index_redirect() -> RedirectResponse:
        return _canonical_redirect(f"{_prefix}/")

    app.add_api_route(_prefix, _index_redirect, include_in_schema=False)
    app.include_router(index_router, prefix=_prefix, include_in_schema=False)

    async def _root_redirect() -> RedirectResponse:
        return _canonical_redirect(f"{_prefix}/")

    app.add_api_route("/", _root_redirect, include_in_schema=False)
    app.mount(
        f"{_prefix}/webfonts", StaticFiles(directory=settings.fonts_dir), name="blog-webfonts"
    )
    app.mount(f"{_prefix}/static", StaticFiles(directory=settings.static_dir), name="blog-static")
    if not _site_config.media.location:
        app.mount(
            f"{_prefix}/media", StaticFiles(directory=settings.uploads_dir), name="blog-media"
        )
else:
    app.include_router(index_router)

if _admin_available:

    async def _admin_redirect() -> RedirectResponse:
        return _canonical_redirect(f"{_prefix}/plym-admin/")

    app.add_api_route(f"{_prefix}/plym-admin", _admin_redirect, include_in_schema=False)
    app.mount(
        f"{_prefix}/plym-admin",
        AdminSPA(str(_admin_dir), f"{_prefix}/plym-admin"),
        name="blog-admin",
    )

app.mount("/webfonts", StaticFiles(directory=settings.fonts_dir), name="webfonts")
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
if not _site_config.media.location:
    app.mount("/media", StaticFiles(directory=settings.uploads_dir), name="media")

if _admin_available:
    app.mount("/admin", AdminSPA(str(_admin_dir), "/admin"), name="admin")

# Last: `/{category}/{slug}` matches any two segments, so every mount above it
# — including the unprefixed ones — would otherwise be answered by the post
# route and 404 as `posts.not_found`.
app.include_router(blog_posts_router, prefix=_site_config.blog_prefix)

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session
from plym.api.state import bundled_css, prism_js, site_config
from plym.config.site import SiteConfig
from plym.exceptions.posts import PostNotFoundError
from plym.render.cache import get_store
from plym.service.post_service import PostService
from plym.settings import settings

index_router = APIRouter(tags=["blog"])
posts_router = APIRouter(tags=["blog"])


def _with_cache_header(html: str, header: str | None) -> HTMLResponse:
    response = HTMLResponse(content=html)
    if header:
        response.headers["Cache-Control"] = header
    return response


@index_router.get("/", response_class=HTMLResponse)
async def serve_index(
    page: int = Query(1, ge=1),
    site: SiteConfig = Depends(site_config),
    css: str = Depends(bundled_css),
    prism: str = Depends(prism_js),
    session: AsyncSession = Depends(db_session),
) -> HTMLResponse:
    store = get_store()
    key = f"index:{page}:{site.pagination.page_size}"
    cached = store.get(key)
    if cached is not None:
        return _with_cache_header(cached, site.http_cache.header_for_index())

    service = PostService(session, site, css, prism)
    items, _ = await service.list_published(page=page, page_size=site.pagination.page_size)
    html = service.render_index([item.model_dump() for item in items])
    store.set(key, html)
    return _with_cache_header(html, site.http_cache.header_for_index())


@posts_router.get("/{slug}", response_class=HTMLResponse)
async def serve_post(
    slug: str,
    site: SiteConfig = Depends(site_config),
) -> HTMLResponse:
    target = settings.generated_dir / f"{slug}.html"
    if not target.exists():
        raise PostNotFoundError()
    content = target.read_text(encoding="utf-8")
    return _with_cache_header(content, site.http_cache.header_for_post())

import hashlib
import re

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session
from plym.api.state import bundled_css, prism_js, site_config
from plym.config.site import SiteConfig
from plym.exceptions.posts import PostNotFoundError
from plym.render.cache import get_store
from plym.render.cache_policy import CachePolicy
from plym.render.urls import is_path_segment, post_path
from plym.service.post_service import PostService
from plym.settings import settings

index_router = APIRouter(tags=["Blog"], include_in_schema=False)
posts_router = APIRouter(tags=["Blog"], include_in_schema=False)

_ACCEPTS_MARKDOWN = re.compile(r"(^|,)\s*text/markdown\s*(;[^,]*)?($|,)", re.IGNORECASE)


def _with_cache_header(html: str, policy: CachePolicy) -> HTMLResponse:
    response = HTMLResponse(content=html)
    response.headers["Cache-Control"] = policy.value
    response.headers["Vary"] = "Accept"
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
        return _with_cache_header(cached, CachePolicy.LISTING)

    service = PostService(session, site, css, prism)
    items, _ = await service.list_published(page=page, page_size=site.pagination.page_size)
    if not items and page > 1:
        raise PostNotFoundError()
    html = service.render_index([item.model_dump() for item in items])
    store.set(key, html)
    return _with_cache_header(html, CachePolicy.LISTING)


def _not_found() -> Response:
    raise PostNotFoundError()


def _etag(content: str) -> str:
    return f'"{hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]}"'


def _matches_etag(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    candidates = [candidate.strip() for candidate in if_none_match.split(",")]
    return "*" in candidates or any(c.removeprefix("W/") == etag for c in candidates)


def _serve_markdown(path: str, *, vary: bool, if_none_match: str | None) -> Response | None:
    source = settings.generated_dir / f"{path}.md"
    if not source.exists():
        return None
    content = source.read_text(encoding="utf-8")
    etag = _etag(content)
    headers = {"ETag": etag, "Cache-Control": CachePolicy.MARKDOWN.value}
    if vary:
        headers["Vary"] = "Accept"
    if _matches_etag(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return PlainTextResponse(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )


def _split_markdown_suffix(slug: str) -> tuple[str, bool]:
    return (slug[:-3], True) if slug.endswith(".md") else (slug, False)


def _serve_markdown_url(path: str, site: SiteConfig, if_none_match: str | None) -> Response:
    if not site.md_urls.enabled:
        raise PostNotFoundError()
    return _serve_markdown(path, vary=False, if_none_match=if_none_match) or _not_found()


def _serve_generated(path: str, accept: str | None, if_none_match: str | None) -> Response:
    if accept and _ACCEPTS_MARKDOWN.search(accept):
        response = _serve_markdown(path, vary=True, if_none_match=if_none_match)
        if response is not None:
            return response
    target = settings.generated_dir / f"{path}.html"
    if not target.exists():
        raise PostNotFoundError()
    content = target.read_text(encoding="utf-8")
    return _with_cache_header(content, CachePolicy.PAGE)


@posts_router.get("/{slug}", response_class=HTMLResponse)
async def serve_post(
    slug: str,
    site: SiteConfig = Depends(site_config),
    accept: str | None = Header(default=None),
    if_none_match: str | None = Header(default=None),
) -> Response:
    slug, as_markdown = _split_markdown_suffix(slug)
    if not is_path_segment(slug):
        raise PostNotFoundError()
    path = post_path(None, slug)
    if as_markdown:
        return _serve_markdown_url(path, site, if_none_match)
    return _serve_generated(path, accept, if_none_match)


@posts_router.get("/{category}/{slug}", response_class=HTMLResponse)
async def serve_categorised_post(
    category: str,
    slug: str,
    site: SiteConfig = Depends(site_config),
    accept: str | None = Header(default=None),
    if_none_match: str | None = Header(default=None),
) -> Response:
    slug, as_markdown = _split_markdown_suffix(slug)
    if not (is_path_segment(category) and is_path_segment(slug)):
        raise PostNotFoundError()
    path = post_path(category, slug)
    if as_markdown:
        return _serve_markdown_url(path, site, if_none_match)
    return _serve_generated(path, accept, if_none_match)

import hashlib
import re
from math import ceil

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session
from plym.api.state import bundled_css, prism_js, site_config
from plym.config.site import SiteConfig
from plym.exceptions.posts import PostNotFoundError
from plym.render.cache import get_store
from plym.render.cache_policy import REDIRECT_CACHE_CONTROL, CachePolicy
from plym.render.urls import (
    INDEX_PAGE_SEGMENT,
    index_path,
    index_url,
    is_path_segment,
    post_path,
)
from plym.service.post_service import PostService
from plym.settings import settings

index_router = APIRouter(tags=["Blog"], include_in_schema=False)
posts_router = APIRouter(tags=["Blog"], include_in_schema=False)

_ACCEPTS_MARKDOWN = re.compile(r"(^|,)\s*text/markdown\s*(;[^,]*)?($|,)", re.IGNORECASE)


def _canonical_redirect(location: str) -> RedirectResponse:
    return RedirectResponse(
        location, status_code=308, headers={"Cache-Control": REDIRECT_CACHE_CONTROL}
    )


def _with_cache_header(html: str, policy: CachePolicy) -> HTMLResponse:
    response = HTMLResponse(content=html)
    response.headers["Cache-Control"] = policy.value
    response.headers["Vary"] = "Accept"
    return response


@index_router.get("/", response_class=HTMLResponse)
async def serve_index(
    page: int | None = Query(None, ge=1),
    site: SiteConfig = Depends(site_config),
    css: str = Depends(bundled_css),
    prism: str = Depends(prism_js),
    session: AsyncSession = Depends(db_session),
    accept: str | None = Header(default=None),
    if_none_match: str | None = Header(default=None),
) -> Response:
    # A purgeable edge cache has to drop the query string from its key, or ?page=2 and
    # every other variant become entries a purge by URL cannot reach. Paginating on the
    # query and being an artifact cannot both be true, so the path form is canonical.
    if page is not None:
        return _canonical_redirect(index_url(site.blog_prefix, page))
    return await _serve_index_page(1, site, css, prism, session, accept, if_none_match)


@index_router.get(f"/{INDEX_PAGE_SEGMENT}/{{page}}", response_class=HTMLResponse)
async def serve_index_page(
    page: int,
    site: SiteConfig = Depends(site_config),
    css: str = Depends(bundled_css),
    prism: str = Depends(prism_js),
    session: AsyncSession = Depends(db_session),
    accept: str | None = Header(default=None),
    if_none_match: str | None = Header(default=None),
) -> Response:
    if page < 2:
        return _canonical_redirect(index_url(site.blog_prefix, 1))
    return await _serve_index_page(page, site, css, prism, session, accept, if_none_match)


async def _serve_index_page(
    page: int,
    site: SiteConfig,
    css: str,
    prism: str,
    session: AsyncSession,
    accept: str | None,
    if_none_match: str | None,
) -> Response:
    relative = index_path(page)
    if accept and _ACCEPTS_MARKDOWN.search(accept):
        negotiated = _serve_markdown(relative, vary=True, if_none_match=if_none_match)
        if negotiated is not None:
            return negotiated

    artifact = settings.generated_dir / f"{relative}.html"
    if artifact.exists():
        return _with_cache_header(artifact.read_text(encoding="utf-8"), CachePolicy.LISTING)

    return await _render_index_page(page, site, css, prism, session)


async def _render_index_page(
    page: int, site: SiteConfig, css: str, prism: str, session: AsyncSession
) -> HTMLResponse:
    page_size = site.pagination.page_size
    store = get_store()
    key = f"index:{page}:{page_size}"
    cached = store.get(key)
    if cached is not None:
        return _with_cache_header(cached, CachePolicy.LISTING)

    service = PostService(session, site, css, prism)
    items, total = await service.list_published(page=page, page_size=page_size)
    if not items and page > 1:
        raise PostNotFoundError()
    pages = max(1, ceil(total / page_size))
    html = service.render_index([item.model_dump() for item in items], page=page, pages=pages)
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

from typing import Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session
from plym.api.state import site_config
from plym.config.site import SiteConfig
from plym.exceptions.posts import PostNotFoundError
from plym.render.urls import path_for_row
from plym.repository.post_repository import PostRepository

router = APIRouter(tags=["SEO"], include_in_schema=False)


_MD_ESCAPES = str.maketrans({"\\": "\\\\", "[": "\\[", "]": "\\]", "(": "\\(", ")": "\\)"})


def _collapse(value: str) -> str:
    return " ".join(value.split())


def _markdown_text(value: str) -> str:
    return _collapse(value).translate(_MD_ESCAPES)


def _llms_entry(base: str, row: dict[str, Any]) -> str:
    entry = f"- [{_markdown_text(row['title'])}]({base}/{path_for_row(row)})"
    if row.get("excerpt"):
        entry = f"{entry}: {_markdown_text(row['excerpt'])}"
    return entry


def _llms_body(site: SiteConfig, base: str, entries: list[str]) -> str:
    sections = [f"# {site.name}"]
    if site.description:
        sections.append(f"> {_collapse(site.description)}")
    sections.append(f"- [{_markdown_text(site.name)}]({base}/)")
    if entries:
        sections.append("## Posts")
        sections.append("\n".join(entries))
    return "\n\n".join(sections) + "\n"


@router.get("/sitemap.xml")
async def sitemap(
    site: SiteConfig = Depends(site_config),
    session: AsyncSession = Depends(db_session),
) -> Response:
    base = escape(site.public_blog_url())
    posts = PostRepository(session)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    lines.append("  <url>")
    lines.append(f"    <loc>{base}/</loc>")
    lines.append("    <changefreq>daily</changefreq>")
    lines.append("  </url>")
    after = 0
    while True:
        chunk = await posts.list_published_slugs_after(after=after, limit=1000)
        if not chunk:
            break
        for row in chunk:
            path = escape(path_for_row(row))
            lastmod = row.get("updated_at") or row.get("published_at")
            lines.append("  <url>")
            lines.append(f"    <loc>{base}/{path}</loc>")
            if lastmod is not None:
                lines.append(f"    <lastmod>{lastmod.date().isoformat()}</lastmod>")
            lines.append("    <changefreq>weekly</changefreq>")
            lines.append("  </url>")
        after = chunk[-1]["id"]
        if len(chunk) < 1000:
            break
    lines.append("</urlset>")
    body = "\n".join(lines)
    headers = {}
    header = site.http_cache.header_for_index()
    if header:
        headers["Cache-Control"] = header
    return Response(content=body, media_type="application/xml", headers=headers)


@router.get("/llms.txt")
async def llms_txt(
    site: SiteConfig = Depends(site_config),
    session: AsyncSession = Depends(db_session),
) -> Response:
    base = site.public_blog_url()
    posts = PostRepository(session)

    entries: list[str] = []
    after = 0
    while True:
        chunk = await posts.list_published_meta_after(after=after, limit=1000)
        if not chunk:
            break
        entries.extend(_llms_entry(base, row) for row in chunk)
        after = chunk[-1]["id"]
        if len(chunk) < 1000:
            break

    body = _llms_body(site, base, entries)
    headers = {}
    header = site.http_cache.header_for_index()
    if header:
        headers["Cache-Control"] = header
    return Response(content=body, media_type="text/markdown", headers=headers)


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots(site: SiteConfig = Depends(site_config)) -> PlainTextResponse:
    if not site.robots.serve:
        raise PostNotFoundError()
    lines = ["User-agent: *"]
    for path in site.robots.disallow_paths:
        lines.append(f"Disallow: {path}")
    lines.append("")
    lines.append(f"Sitemap: {site.public_blog_url()}/sitemap.xml")
    body = "\n".join(lines) + "\n"
    return PlainTextResponse(content=body)

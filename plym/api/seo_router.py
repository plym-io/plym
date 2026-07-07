from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session
from plym.api.state import site_config
from plym.config.site import SiteConfig
from plym.exceptions.posts import PostNotFoundError
from plym.repository.post_repository import PostRepository

router = APIRouter(tags=["SEO"], include_in_schema=False)


def _collapse(value: str) -> str:
    return " ".join(value.split())


def _llms_entry(base: str, row: dict) -> str:
    title = _collapse(row["title"]).replace("[", "\\[").replace("]", "\\]")
    entry = f"- [{title}]({base}/{row['slug']})"
    if row.get("excerpt"):
        entry = f"{entry}: {_collapse(row['excerpt'])}"
    return entry


@router.get("/sitemap.xml")
async def sitemap(
    site: SiteConfig = Depends(site_config),
    session: AsyncSession = Depends(db_session),
) -> Response:
    base = site.public_blog_url()
    posts = PostRepository(session)

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lines.append("  <url>")
    lines.append(f"    <loc>{escape(base)}/</loc>")
    lines.append("    <changefreq>daily</changefreq>")
    lines.append("  </url>")
    after = 0
    while True:
        chunk = await posts.list_published_slugs_after(after=after, limit=1000)
        if not chunk:
            break
        for row in chunk:
            slug = escape(row["slug"])
            lastmod = (row.get("updated_at") or row.get("published_at"))
            lines.append("  <url>")
            lines.append(f"    <loc>{base}/{slug}</loc>")
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

    entries = []
    after = 0
    while True:
        chunk = await posts.list_published_meta_after(after=after, limit=1000)
        if not chunk:
            break
        entries.extend(_llms_entry(base, row) for row in chunk)
        after = chunk[-1]["id"]
        if len(chunk) < 1000:
            break

    sections = [f"# {site.name}"]
    if site.description:
        sections.append(f"> {_collapse(site.description)}")
    sections.append("## Posts")
    if entries:
        sections.append("\n".join(entries))
    body = "\n\n".join(sections) + "\n"
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

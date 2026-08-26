from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy.ext.asyncio import AsyncSession

from plym.config.site import SiteConfig
from plym.instrumentation.tracer import Traced
from plym.render.excerpt import resolve_excerpt
from plym.render.urls import path_for_row
from plym.repository.post_repository import PostRepository
from plym.service.artifact_writer import write_if_changed
from plym.service.index_artifact_service import IndexArtifactService
from plym.service.post_pipeline import PostPipeline
from plym.service.search_index_service import SearchIndexService
from plym.settings import settings

SITEMAP_FILE = "sitemap.xml"
LLMS_FILE = "llms.txt"
ROBOTS_FILE = "robots.txt"

_BATCH_SIZE = 1000
_MD_ESCAPES = str.maketrans({"\\": "\\\\", "[": "\\[", "]": "\\]", "(": "\\(", ")": "\\)"})


def _collapse(value: str) -> str:
    return " ".join(value.split())


def _markdown_text(value: str) -> str:
    return _collapse(value).translate(_MD_ESCAPES)


def _llms_entry(base: str, row: dict[str, Any]) -> str:
    entry = f"- [{_markdown_text(row['title'])}]({base}/{path_for_row(row)})"
    excerpt = resolve_excerpt(row.get("excerpt"), row["content"])
    if excerpt:
        entry = f"{entry}: {_markdown_text(excerpt)}"
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


class SiteFilesService(Traced):
    def __init__(self, session: AsyncSession, site: SiteConfig) -> None:
        self._posts = PostRepository(session)
        self._site = site

    async def sitemap(self) -> str:
        base = escape(self._site.public_blog_url())
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            "  <url>",
            f"    <loc>{base}/</loc>",
            "    <changefreq>daily</changefreq>",
            "  </url>",
        ]
        after = 0
        while True:
            chunk = await self._posts.list_published_slugs_after(after=after, limit=_BATCH_SIZE)
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
            if len(chunk) < _BATCH_SIZE:
                break
        lines.append("</urlset>")
        return "\n".join(lines)

    async def llms_txt(self) -> str:
        base = self._site.public_blog_url()
        entries: list[str] = []
        after = 0
        while True:
            chunk = await self._posts.list_published_meta_after(after=after, limit=_BATCH_SIZE)
            if not chunk:
                break
            entries.extend(_llms_entry(base, row) for row in chunk)
            after = chunk[-1]["id"]
            if len(chunk) < _BATCH_SIZE:
                break
        return _llms_body(self._site, base, entries)

    def robots_txt(self) -> str | None:
        if not self._site.robots.serve:
            return None
        lines = ["User-agent: *"]
        lines.extend(f"Disallow: {path}" for path in self._site.robots.disallow_paths)
        lines.append("")
        lines.append(f"Sitemap: {self._site.public_blog_url()}/{SITEMAP_FILE}")
        return "\n".join(lines) + "\n"

    async def write(self) -> None:
        await write_if_changed(_artifact(SITEMAP_FILE), await self.sitemap())
        await write_if_changed(_artifact(LLMS_FILE), await self.llms_txt())
        await write_if_changed(_artifact(ROBOTS_FILE), self.robots_txt())


def _artifact(name: str) -> Path:
    return settings.generated_dir / name


async def refresh_site_artifacts(
    session: AsyncSession, site: SiteConfig, pipeline: PostPipeline
) -> None:
    await IndexArtifactService(session, site, pipeline).write()
    await SiteFilesService(session, site).write()
    await SearchIndexService(session, site).refresh()

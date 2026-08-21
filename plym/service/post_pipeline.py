import json
from datetime import datetime
from typing import Any

import aiofiles
from slugify import slugify

from plym.config.site import SiteConfig
from plym.render.cache import get_store
from plym.render.excerpt import resolve_excerpt
from plym.render.html_assembler import HtmlAssembler
from plym.render.index_markdown import render_index_markdown
from plym.render.llms import llms_directive, llms_txt_url
from plym.render.markdown_renderer import MarkdownRenderer
from plym.render.reading_time import ReadingTimeCalculator
from plym.render.stamp import compute_render_stamp
from plym.render.template_renderer import TemplateRenderer
from plym.render.urls import index_url, post_path
from plym.settings import settings


class PostRenderResult:
    def __init__(self, *, html: str, rendered_path: str | None, reading_time: int) -> None:
        self.html = html
        self.rendered_path = rendered_path
        self.reading_time = reading_time


class PostPipeline:
    def __init__(self, site: SiteConfig, css: str, prism_js: str) -> None:
        self._site = site
        self._css = css
        self._prism_js = prism_js
        self._markdown = MarkdownRenderer()
        self._template = TemplateRenderer(site)
        self._reading = ReadingTimeCalculator(site.reading.words_per_minute)
        self._store = get_store()
        self._stamp = compute_render_stamp(site, css, prism_js)
        self._llms_url = llms_txt_url(site.public_blog_url())

    @property
    def render_stamp(self) -> str:
        return self._stamp

    def slugify(self, value: str) -> str:
        return slugify(value, regex_pattern=r"[^a-z0-9]+")

    def _faq_jsonld(self, faqs: list[dict[str, Any]]) -> str | None:
        if not faqs:
            return None
        payload = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": faq["question"],
                    "acceptedAnswer": {"@type": "Answer", "text": faq["answer"]},
                }
                for faq in faqs
            ],
        }
        return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    def _person_jsonld(self, author: dict[str, Any]) -> dict[str, Any]:
        person: dict[str, Any] = {"@type": "Person", "name": author.get("display_name")}
        if author.get("avatar_url"):
            person["image"] = author["avatar_url"]
        same_as = [link["url"] for link in author.get("links") or []]
        if same_as:
            person["sameAs"] = same_as
        return person

    def _publisher_jsonld(self) -> dict[str, Any]:
        publisher: dict[str, Any] = {"@type": "Organization", "name": self._site.name}
        if self._site.logo:
            publisher["logo"] = {
                "@type": "ImageObject",
                "url": self._site.absolute_url(self._site.logo),
            }
        return publisher

    def _article_jsonld(
        self,
        *,
        title: str,
        excerpt: str | None,
        cover: str | None,
        canonical: str,
        author: dict[str, Any],
        published_at: datetime | None,
        updated_at: datetime | None,
    ) -> str:
        payload: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": title,
            "url": canonical,
            "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
            "author": self._person_jsonld(author),
            "publisher": self._publisher_jsonld(),
        }
        if excerpt:
            payload["description"] = excerpt
        if cover:
            payload["image"] = cover
        if published_at:
            payload["datePublished"] = published_at.isoformat()
        if updated_at:
            payload["dateModified"] = updated_at.isoformat()
        return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    def reading_minutes(self, content: str) -> int:
        return self._reading.minutes(content)

    def _markdown_artifact(self, content: str) -> str:
        return f"{content.rstrip()}\n\n{llms_directive(self._llms_url)}\n"

    def _build_post_context(
        self,
        *,
        slug: str,
        title: str,
        content: str,
        content_html: str,
        excerpt: str | None,
        cover: str | None,
        canonical_url: str | None,
        author: dict[str, Any],
        reading_time: int,
        published_at: datetime | None,
        updated_at: datetime | None,
        tags: list[dict[str, Any]],
        faqs: list[dict[str, Any]],
        toc: list[dict[str, Any]],
        category: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = post_path(category["slug"] if category else None, slug)
        canonical = canonical_url or f"{self._site.public_blog_url()}/{path}"
        excerpt = resolve_excerpt(excerpt, content)
        if cover:
            cover = self._site.absolute_url(cover)
        return {
            "post": {
                "slug": slug,
                "path": path,
                "category": category,
                "name": title,
                "title": title,
                "content": content_html,
                "excerpt": excerpt,
                "cover": cover,
                "canonical": canonical,
                "canonical_url": canonical_url,
                "author": author,
                "reading_time": reading_time,
                "published_at": published_at,
                "updated_at": updated_at,
                "tags": tags,
                "faqs": faqs,
                "faq_jsonld": self._faq_jsonld(faqs),
                "article_jsonld": self._article_jsonld(
                    title=title,
                    excerpt=excerpt,
                    cover=cover,
                    canonical=canonical,
                    author=author,
                    published_at=published_at,
                    updated_at=updated_at,
                ),
                "toc": toc,
            },
            "render_stamp": self._stamp,
        }

    async def render_and_persist(
        self,
        *,
        slug: str,
        title: str,
        content: str,
        excerpt: str | None,
        cover: str | None,
        canonical_url: str | None,
        author: dict[str, Any],
        published_at: datetime | None,
        updated_at: datetime | None,
        tags: list[dict[str, Any]],
        faqs: list[dict[str, Any]],
        category: dict[str, Any] | None = None,
    ) -> PostRenderResult:
        content_html, toc = self._markdown.render(content)
        reading_time = self._reading.minutes(content)
        context = self._build_post_context(
            slug=slug,
            title=title,
            content=content,
            content_html=content_html,
            excerpt=excerpt,
            cover=cover,
            canonical_url=canonical_url,
            author=author,
            reading_time=reading_time,
            published_at=published_at,
            updated_at=updated_at,
            tags=tags,
            faqs=faqs,
            toc=toc,
            category=category,
        )
        rendered = self._template.render_post(context)
        final = HtmlAssembler.inline_assets(
            rendered,
            self._css,
            self._prism_js,
            inject_head=self._site.inject.head,
            inject_body=self._site.inject.body,
            llms_url=self._llms_url,
        )

        path = post_path(category["slug"] if category else None, slug)
        target = settings.generated_dir / f"{path}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".html.tmp")
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write(final)
        tmp.replace(target)

        md_target = settings.generated_dir / f"{path}.md"
        md_tmp = md_target.with_suffix(".md.tmp")
        async with aiofiles.open(md_tmp, "w", encoding="utf-8") as f:
            await f.write(self._markdown_artifact(content))
        md_tmp.replace(md_target)

        self._store.delete_prefix("index:")
        return PostRenderResult(
            html=final,
            rendered_path=str(target),
            reading_time=reading_time,
        )

    async def render_row(self, row: dict[str, Any]) -> PostRenderResult:
        return await self.render_and_persist(
            slug=row["slug"],
            title=row["title"],
            content=row["content"],
            excerpt=row.get("excerpt"),
            cover=row.get("cover"),
            canonical_url=row.get("canonical_url"),
            author={
                "display_name": row["display_name"],
                "avatar_url": row.get("avatar_url"),
                "links": row.get("links") or [],
            },
            published_at=row.get("published_at"),
            updated_at=row.get("updated_at"),
            tags=row["tags"],
            faqs=row["faqs"],
            category=row.get("category"),
        )

    def index_pagination(self, page: int, pages: int) -> dict[str, Any]:
        prefix = self._site.blog_prefix
        base = self._site.public_blog_url()
        return {
            "page": page,
            "pages": pages,
            "prev_url": index_url(prefix, page - 1) if page > 1 else None,
            "next_url": index_url(prefix, page + 1) if page < pages else None,
            "canonical": f"{base}{index_url('', page)}",
        }

    def render_index(self, posts: list[dict[str, Any]], page: int = 1, pages: int = 1) -> str:
        pagination = self.index_pagination(page, pages)
        rendered = self._template.render_index({"posts": posts, "pagination": pagination})
        return HtmlAssembler.inline_assets(
            rendered,
            self._css,
            self._prism_js,
            inject_head=self._site.inject.head,
            inject_body=self._site.inject.body,
            llms_url=self._llms_url,
        )

    def render_index_markdown(
        self, posts: list[dict[str, Any]], page: int = 1, pages: int = 1
    ) -> str:
        pagination = self.index_pagination(page, pages)
        return render_index_markdown(
            name=self._site.name,
            description=self._site.description,
            base=self._site.public_blog_url(),
            posts=posts,
            page=page,
            pages=pages,
            prev_url=pagination["prev_url"],
            next_url=pagination["next_url"],
        )

    def render_preview(
        self,
        *,
        title: str,
        content: str,
        excerpt: str | None,
        cover: str | None,
        canonical_url: str | None = None,
    ) -> str:
        content_html, toc = self._markdown.render(content)
        reading_time = self._reading.minutes(content)
        context = self._build_post_context(
            slug="preview",
            title=title,
            content=content,
            content_html=content_html,
            excerpt=excerpt,
            cover=cover,
            canonical_url=canonical_url,
            author={"display_name": "Preview", "avatar_url": None, "links": []},
            reading_time=reading_time,
            published_at=None,
            updated_at=None,
            tags=[],
            faqs=[],
            toc=toc,
        )
        rendered = self._template.render_post(context)
        return HtmlAssembler.inline_assets(
            rendered,
            self._css,
            self._prism_js,
            inject_head=self._site.inject.head,
            inject_body=self._site.inject.body,
            llms_url=self._llms_url,
        )

    def invalidate_index(self) -> None:
        self._store.delete_prefix("index:")

    def remove_rendered(self, slug: str, category_slug: str | None = None) -> None:
        relative = post_path(category_slug, slug)
        for suffix in (".html", ".md"):
            path = settings.generated_dir / f"{relative}{suffix}"
            if path.exists():
                path.unlink()
        parent = (settings.generated_dir / relative).parent
        if parent != settings.generated_dir and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
        self._store.delete_prefix("index:")

    def index_cache_get(self, key: str) -> str | None:
        return self._store.get(key)

    def index_cache_set(self, key: str, value: str) -> None:
        self._store.set(key, value)

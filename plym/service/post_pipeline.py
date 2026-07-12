import json
from datetime import datetime

import aiofiles
from slugify import slugify

from plym.config.site import SiteConfig
from plym.render.cache import get_store
from plym.render.html_assembler import HtmlAssembler
from plym.render.markdown_renderer import MarkdownRenderer
from plym.render.reading_time import ReadingTimeCalculator
from plym.render.stamp import compute_render_stamp
from plym.render.template_renderer import TemplateRenderer
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

    @property
    def render_stamp(self) -> str:
        return self._stamp

    def slugify(self, value: str) -> str:
        return slugify(value, regex_pattern=r"[^a-z0-9]+")

    def _faq_jsonld(self, faqs: list[dict]) -> str | None:
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

    def _person_jsonld(self, author: dict) -> dict:
        person: dict = {"@type": "Person", "name": author.get("display_name")}
        if author.get("avatar_url"):
            person["image"] = author["avatar_url"]
        same_as = [link["url"] for link in author.get("links") or []]
        if same_as:
            person["sameAs"] = same_as
        return person

    def _publisher_jsonld(self) -> dict:
        publisher: dict = {"@type": "Organization", "name": self._site.name}
        if self._site.logo:
            publisher["logo"] = {"@type": "ImageObject", "url": self._site.logo}
        return publisher

    def _article_jsonld(
        self,
        *,
        title: str,
        excerpt: str | None,
        cover: str | None,
        canonical: str,
        author: dict,
        published_at: datetime | None,
        updated_at: datetime | None,
    ) -> str:
        payload: dict = {
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

    def _build_post_context(
        self,
        *,
        slug: str,
        title: str,
        content_html: str,
        excerpt: str | None,
        cover: str | None,
        canonical_url: str | None,
        author: dict,
        reading_time: int,
        published_at: datetime | None,
        updated_at: datetime | None,
        tags: list[dict],
        faqs: list[dict],
        toc: list[dict],
    ) -> dict:
        canonical = canonical_url or f"{self._site.public_blog_url()}/{slug}"
        if cover:
            cover = self._site.absolute_url(cover)
        return {
            "post": {
                "slug": slug,
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
        author: dict,
        published_at: datetime | None,
        updated_at: datetime | None,
        tags: list[dict],
        faqs: list[dict],
    ) -> PostRenderResult:
        content_html, toc = self._markdown.render(content)
        reading_time = self._reading.minutes(content)
        context = self._build_post_context(
            slug=slug,
            title=title,
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
        )
        rendered = self._template.render_post(context)
        final = HtmlAssembler.inline_assets(
            rendered,
            self._css,
            self._prism_js,
            inject_head=self._site.inject.head,
            inject_body=self._site.inject.body,
        )

        target = settings.generated_dir / f"{slug}.html"
        tmp = target.with_suffix(".html.tmp")
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write(final)
        tmp.replace(target)

        md_target = settings.generated_dir / f"{slug}.md"
        md_tmp = md_target.with_suffix(".md.tmp")
        async with aiofiles.open(md_tmp, "w", encoding="utf-8") as f:
            await f.write(content)
        md_tmp.replace(md_target)

        self._store.delete_prefix("index:")
        return PostRenderResult(
            html=final,
            rendered_path=str(target),
            reading_time=reading_time,
        )

    def render_index(self, posts: list[dict]) -> str:
        rendered = self._template.render_index({"posts": posts})
        return HtmlAssembler.inline_assets(
            rendered,
            self._css,
            self._prism_js,
            inject_head=self._site.inject.head,
            inject_body=self._site.inject.body,
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
        )

    def invalidate_index(self) -> None:
        self._store.delete_prefix("index:")

    def remove_rendered(self, slug: str) -> None:
        path = settings.generated_dir / f"{slug}.html"
        if path.exists():
            path.unlink()
        md_path = settings.generated_dir / f"{slug}.md"
        if md_path.exists():
            md_path.unlink()
        self._store.delete_prefix("index:")

    def index_cache_get(self, key: str) -> str | None:
        return self._store.get(key)

    def index_cache_set(self, key: str, value: str) -> None:
        self._store.set(key, value)

import os
from typing import Any

os.environ.setdefault("PLYM_JWT_SECRET", "plym-default-template-unit-tests")

from plym.config.site import SiteConfig
from plym.render.template_renderer import TemplateRenderer
from plym.settings import settings

PACKAGED = settings.base_dir / "plym" / "templates" / "default"


def test_the_packaged_default_is_the_only_copy_in_the_repo() -> None:
    # The bundled templates live in the package alone; a repo-root templates/
    # dir is a runtime overlay created per install, never tracked. If this
    # fails locally, delete your stale templates/ dir — nothing mounts it now.
    assert not (settings.base_dir / "templates").exists()


def test_both_pages_carry_the_lead_collector() -> None:
    for page in ("index.html", "post.html"):
        assert '{% include "_subscribe.html" %}' in (PACKAGED / page).read_text(encoding="utf-8")


def _index_at(prefix: str) -> str:
    home = f"plym.local{prefix}"
    site = SiteConfig(name="Acme", blog_home=home, blog_prefix=prefix)
    pagination = {
        "page": 1,
        "pages": 1,
        "prev_url": None,
        "next_url": None,
        "canonical": f"https://{home}/",
    }
    return TemplateRenderer(site).render_index({"posts": [], "pagination": pagination})


def test_the_lead_collector_posts_to_the_blogs_own_prefix() -> None:
    assert 'data-endpoint="/blog/api/collect"' in _index_at("/blog")


def test_the_lead_collector_endpoint_stays_root_relative_without_a_prefix() -> None:
    assert 'data-endpoint="/api/collect"' in _index_at("")


LINKS: dict[str, Any] = {
    "header": [
        {"text": "Home", "url": "/"},
        {"text": "Resources", "children": [{"text": "Docs", "url": "https://plym.io/docs/"}]},
    ],
    "footer": [
        {"text": "About", "url": "/about"},
        {"text": "Product", "children": [{"text": "Pricing", "url": "/pricing"}]},
    ],
}


def _post_context() -> dict[str, Any]:
    return {
        "render_stamp": "0123456789abcdef",
        "post": {
            "slug": "hello",
            "path": "hello",
            "category": None,
            "title": "Hello",
            "content": "<p>Hello</p>",
            "excerpt": None,
            "cover": None,
            "canonical": "https://plym.local/hello",
            "author": {"display_name": "Ada", "avatar_url": None, "links": []},
            "reading_time": 1,
            "published_at": None,
            "updated_at": None,
            "tags": [],
            "faqs": [],
            "faq_jsonld": None,
            "article_jsonld": "{}",
            "toc": [],
        },
    }


def _pages(links: dict[str, Any]) -> list[str]:
    renderer = TemplateRenderer(SiteConfig(name="Acme", links=links))
    pagination = {
        "page": 1,
        "pages": 1,
        "prev_url": None,
        "next_url": None,
        "canonical": "https://plym.local/",
    }
    return [
        renderer.render_index({"posts": [], "pagination": pagination}),
        renderer.render_post(_post_context()),
    ]


def test_both_pages_render_the_configured_header_links() -> None:
    for page in _pages(LINKS):
        assert '<a class="plym-nav-link" href="/">Home</a>' in page
        assert '<summary class="plym-nav-summary">Resources</summary>' in page
        assert '<a class="plym-nav-link" href="https://plym.io/docs/">Docs</a>' in page


def test_both_pages_render_the_configured_footer_links() -> None:
    for page in _pages(LINKS):
        assert '<a class="plym-footer-link" href="/about">About</a>' in page
        assert '<p class="plym-footer-group-title">Product</p>' in page
        assert '<a href="/pricing">Pricing</a>' in page


def test_a_blog_without_links_renders_no_navigation() -> None:
    for page in _pages({}):
        assert "plym-nav" not in page
        assert "plym-footer-nav" not in page
        assert "plym-header-navigated" not in page


def test_the_dropdown_script_ships_only_when_a_menu_needs_it() -> None:
    flat: dict[str, Any] = {"header": [{"text": "Home", "url": "/"}]}
    for page in _pages(flat):
        assert "plym-nav-group" not in page
    for page in _pages(LINKS):
        assert "document.querySelectorAll('.plym-nav-group')" in page

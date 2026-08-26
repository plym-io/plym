import os

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

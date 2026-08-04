from pathlib import Path

import pytest

from plym.config.site import SiteConfig, load_site_config, normalize_prefix


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("/blog", "/blog"), ("blog", "/blog"), ("/blog/", "/blog"), ("/", ""), ("", ""), (None, "")],
)
def test_normalize_prefix(raw: str | None, expected: str) -> None:
    assert normalize_prefix(raw) == expected


@pytest.mark.parametrize(
    ("home", "prefix"),
    [
        ("https://t.plym.io", "/"),
        ("https://t.plym.io", ""),
        ("https://t.plym.io/", "/"),
        ("https://t.plym.io/blog", "/blog"),
        ("https://t.plym.io/docs/notes", "/docs/notes"),
    ],
)
def test_agreeing_home_and_prefix_are_accepted(home: str, prefix: str) -> None:
    config = SiteConfig(name="T", blog_home=home, blog_prefix=prefix)
    assert config.blog_prefix == normalize_prefix(prefix)


@pytest.mark.parametrize(
    ("home", "prefix"),
    [
        ("https://t.plym.io/blog", "/docs"),
        ("https://t.plym.io/blog", "/"),
        ("https://t.plym.io", "/blog"),
    ],
)
def test_disagreeing_home_and_prefix_are_rejected(home: str, prefix: str) -> None:
    with pytest.raises(ValueError, match="blog_prefix"):
        SiteConfig(name="T", blog_home=home, blog_prefix=prefix)


def test_prefix_that_would_inject_into_admin_base_href_is_rejected() -> None:
    with pytest.raises(ValueError, match="blog_prefix"):
        SiteConfig(name="T", blog_home="https://t.plym.io", blog_prefix='/a"><script>')


def test_explicit_md_urls_are_disabled_by_default() -> None:
    assert SiteConfig(name="T").md_urls.enabled is False


def _write_config(tmp_path: Path, prefix: str, home: str) -> Path:
    target = tmp_path / "config.yaml"
    target.write_text(f'name: T\nblog_home: "{home}"\nblog_prefix: "{prefix}"\n', encoding="utf-8")
    return target


def test_served_prefix_disagreeing_with_config_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _write_config(tmp_path, "/blog", "https://t.plym.io/blog")
    monkeypatch.setattr("plym.config.site.settings.blog_prefix", "/docs")
    with pytest.raises(ValueError, match="PLYM_BLOG_PREFIX"):
        load_site_config(target)


@pytest.mark.parametrize("served", ["/blog", "blog", "/blog/"])
def test_served_prefix_matching_config_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: str
) -> None:
    target = _write_config(tmp_path, "/blog", "https://t.plym.io/blog")
    monkeypatch.setattr("plym.config.site.settings.blog_prefix", served)
    assert load_site_config(target).blog_prefix == "/blog"


@pytest.mark.parametrize("served", [None, ""])
def test_unset_served_prefix_is_not_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: str | None
) -> None:
    target = _write_config(tmp_path, "/blog", "https://t.plym.io/blog")
    monkeypatch.setattr("plym.config.site.settings.blog_prefix", served)
    assert load_site_config(target).blog_prefix == "/blog"


def test_root_hosted_tenant_boots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = _write_config(tmp_path, "/", "https://t.plym.io")
    monkeypatch.setattr("plym.config.site.settings.blog_prefix", "/")
    config = load_site_config(target)
    assert config.blog_prefix == ""
    assert config.public_blog_url() == "https://t.plym.io"


@pytest.mark.parametrize("prefix", ["/api", "/admin", "/plym-admin", "/media", "/blog/api"])
def test_prefix_may_not_claim_a_segment_the_blog_serves(prefix: str) -> None:
    with pytest.raises(ValueError, match="blog_prefix"):
        SiteConfig(name="T", blog_home=f"https://t.plym.io{prefix}", blog_prefix=prefix)


@pytest.mark.parametrize("prefix", ["/blog", "/docs/notes", "/writing"])
def test_ordinary_prefixes_are_still_accepted(prefix: str) -> None:
    config = SiteConfig(name="T", blog_home=f"https://t.plym.io{prefix}", blog_prefix=prefix)
    assert config.blog_prefix == prefix

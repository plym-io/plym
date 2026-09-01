from pathlib import Path

import pytest

from plym.config.site import NavLink, SiteConfig, load_site_config, normalize_prefix


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


def _write_template(templates: Path, name: str, body: str) -> None:
    (templates / name).mkdir(parents=True)
    (templates / name / "template.yaml").write_text(body, encoding="utf-8")


def _load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: str) -> SiteConfig:
    target = tmp_path / "config.yaml"
    target.write_text(config, encoding="utf-8")
    monkeypatch.setattr("plym.config.site.settings.templates_dir", tmp_path / "templates")
    monkeypatch.setattr("plym.config.site.settings.blog_prefix", "")
    load_site_config.cache_clear()
    try:
        return load_site_config(target)
    finally:
        load_site_config.cache_clear()


def test_a_bare_family_string_still_configures_a_slot() -> None:
    config = SiteConfig(name="T", fonts={"heading": "Roboto"})
    assert config.fonts.heading.family == "Roboto"
    assert config.fonts.heading.weights == {"bold": 600}
    assert config.fonts.body.weights == {"regular": 400}


def test_the_engine_default_is_one_weight_per_slot() -> None:
    config = SiteConfig(name="T")
    assert config.fonts.heading.weights == {"bold": 600}
    assert config.fonts.body.weights == {"regular": 400}


def test_declared_weights_replace_the_default_rather_than_merging() -> None:
    config = SiteConfig(
        name="T", fonts={"heading": {"family": "Fraunces", "weights": {"light": 300}}}
    )
    assert config.fonts.heading.weights == {"light": 300}


def test_every_role_of_the_vocabulary_is_accepted() -> None:
    weights = {"light": 300, "regular": 400, "medium": 500, "bold": 700, "black": 900}
    config = SiteConfig(name="T", fonts={"heading": {"family": "Inter", "weights": weights}})
    assert config.fonts.heading.weights == weights


@pytest.mark.parametrize("role", ["base", "strong", "display", "Bold", "semibold"])
def test_a_role_outside_the_vocabulary_is_rejected(role: str) -> None:
    with pytest.raises(ValueError):
        SiteConfig(name="T", fonts={"heading": {"family": "Inter", "weights": {role: 600}}})


@pytest.mark.parametrize("weight", [0, 1001, "heavy", None])
def test_weights_outside_the_css_range_are_rejected(weight: object) -> None:
    with pytest.raises(ValueError):
        SiteConfig(name="T", fonts={"heading": {"family": "Inter", "weights": {"bold": weight}}})


def test_a_typoed_fonts_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        SiteConfig(name="T", fonts={"heading": {"family": "Inter", "wieghts": {"bold": 600}}})


def test_a_plus_separated_family_is_normalized_to_spaces() -> None:
    config = SiteConfig(name="T", fonts={"heading": "Hanken+Grotesk"})
    assert config.fonts.heading.family == "Hanken Grotesk"


@pytest.mark.parametrize("family", ["Inter'; }", "Inter:wght@400;700", ""])
def test_a_family_that_is_not_a_google_fonts_name_is_rejected(family: str) -> None:
    with pytest.raises(ValueError):
        SiteConfig(name="T", fonts={"heading": family})


def test_the_packaged_default_template_declares_the_weights_it_renders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    load_site_config.cache_clear()
    target = tmp_path / "config.yaml"
    target.write_text('name: T\nblog_home: "https://t.plym.io"\n', encoding="utf-8")
    monkeypatch.setattr("plym.config.site.settings.blog_prefix", "")
    try:
        config = load_site_config(target)
    finally:
        load_site_config.cache_clear()
    assert config.fonts.heading.weights == {"bold": 600, "black": 900}
    assert config.fonts.body.weights == {"regular": 400}


def test_a_template_declaring_no_weights_keeps_the_pair_plym_shipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_template(tmp_path / "templates", "custom", "fonts:\n  heading: Fraunces\n")
    config = _load(
        tmp_path, monkeypatch, 'name: T\nblog_home: "https://t.plym.io"\ntemplate: custom\n'
    )
    assert config.fonts.heading.family == "Fraunces"
    assert config.fonts.heading.weights == {"bold": 600, "black": 900}
    assert config.fonts.body.weights == {"regular": 400}


def test_a_template_with_no_yaml_at_all_keeps_the_pair_plym_shipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "templates" / "bare").mkdir(parents=True)
    config = _load(
        tmp_path, monkeypatch, 'name: T\nblog_home: "https://t.plym.io"\ntemplate: bare\n'
    )
    assert config.fonts.heading.family == "Inter"
    assert config.fonts.heading.weights == {"bold": 600, "black": 900}
    assert config.fonts.body.weights == {"regular": 400}


def test_a_template_declaring_weights_gets_exactly_those(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_template(
        tmp_path / "templates",
        "custom",
        "fonts:\n  heading:\n    family: Fraunces\n    weights:\n      medium: 500\n",
    )
    config = _load(
        tmp_path, monkeypatch, 'name: T\nblog_home: "https://t.plym.io"\ntemplate: custom\n'
    )
    assert config.fonts.heading.weights == {"medium": 500}
    assert config.fonts.body.weights == {"regular": 400}


def test_an_operator_family_string_keeps_the_template_weights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_template(
        tmp_path / "templates",
        "custom",
        "fonts:\n  heading:\n    family: Fraunces\n    weights:\n      black: 950\n",
    )
    config = _load(
        tmp_path,
        monkeypatch,
        'name: T\nblog_home: "https://t.plym.io"\ntemplate: custom\nfonts:\n  heading: Roboto\n',
    )
    assert config.fonts.heading.family == "Roboto"
    assert config.fonts.heading.weights == {"black": 950}


def test_operator_weights_override_the_shim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_template(tmp_path / "templates", "custom", "fonts:\n  heading: Fraunces\n")
    config = _load(
        tmp_path,
        monkeypatch,
        'name: T\nblog_home: "https://t.plym.io"\ntemplate: custom\n'
        "fonts:\n  heading:\n    weights:\n      medium: 500\n",
    )
    assert config.fonts.heading.family == "Fraunces"
    assert config.fonts.heading.weights == {"medium": 500}


def test_header_and_footer_links_carry_their_nesting() -> None:
    config = SiteConfig(
        name="T",
        links={
            "header": {
                "Home": "/",
                "Resources": {"Docs": "https://plym.io/docs/"},
            },
            "footer": {"About": "/about"},
        },
    )
    assert [link.text for link in config.links.header] == ["Home", "Resources"]
    assert config.links.header[1].children[0].url == "https://plym.io/docs/"
    assert config.links.footer[0].url == "/about"


def test_a_nested_block_may_also_be_written_as_a_list_of_pairs() -> None:
    config = SiteConfig(
        name="T",
        links={"header": {"Resources": [{"Docs": "/docs"}, {"Tools": "/tools"}]}},
    )
    assert [child.text for child in config.links.header[0].children] == ["Docs", "Tools"]
    assert [child.url for child in config.links.header[0].children] == ["/docs", "/tools"]


def test_links_render_in_the_order_they_are_written() -> None:
    config = SiteConfig(name="T", links={"footer": {"Third": "/3", "First": "/1", "Second": "/2"}})
    assert [link.text for link in config.links.footer] == ["Third", "First", "Second"]


def test_a_site_that_configures_no_links_gets_empty_menus() -> None:
    config = SiteConfig(name="T")
    assert config.links.header == []
    assert config.links.footer == []


def test_a_link_pointing_at_nothing_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be a url"):
        SiteConfig(name="T", links={"header": {"Home": None}})


def test_a_link_cannot_be_both_a_url_and_a_group() -> None:
    with pytest.raises(ValueError, match="cannot be both a url"):
        NavLink(text="Docs", url="/docs", children=[NavLink(text="API", url="/docs/api")])


def test_links_nested_beyond_one_level_are_rejected() -> None:
    with pytest.raises(ValueError, match="one level deep"):
        SiteConfig(name="T", links={"footer": {"Product": {"Docs": {"API": "/api"}}}})


def test_a_link_name_yaml_reads_as_a_boolean_is_rejected() -> None:
    with pytest.raises(ValueError, match="quote it"):
        SiteConfig(name="T", links={"header": {True: "/on"}})


def test_a_list_entry_that_is_not_a_single_pair_is_rejected() -> None:
    with pytest.raises(ValueError, match="single 'Name: url' pair"):
        SiteConfig(name="T", links={"header": {"Resources": [{"Docs": "/docs", "Tools": "/t"}]}})


def test_a_navigation_written_as_a_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="block of 'Name: url' entries"):
        SiteConfig(name="T", links={"header": [{"text": "Home", "url": "/"}]})

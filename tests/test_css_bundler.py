import importlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("PLYM_JWT_SECRET", "plym-css-bundler-unit-tests")

_module = importlib.import_module("plym.build.css_bundler")
minify = _module.minify
CssBundler = _module.CssBundler
CORE_CSS_DIR = _module.CORE_CSS_DIR


def test_clamp_preserves_whitespace_around_plus() -> None:
    assert (
        minify("a{font-size:clamp(1rem, 0.5rem + 2vw, 2rem)}")
        == "a{font-size:clamp(1rem,0.5rem + 2vw,2rem)}"
    )


def test_clamp_preserves_whitespace_around_minus() -> None:
    assert (
        minify("a{width:clamp(1rem, 100% - 2rem, 3rem)}") == "a{width:clamp(1rem,100% - 2rem,3rem)}"
    )


def test_clamp_preserves_nested_calc() -> None:
    assert (
        minify("a{width:clamp(1rem, calc(100% - 2rem), 5rem)}")
        == "a{width:clamp(1rem,calc(100% - 2rem),5rem)}"
    )


def test_min_preserves_whitespace_around_plus() -> None:
    assert minify("a{width:min(1rem + 2vw, 3rem)}") == "a{width:min(1rem + 2vw,3rem)}"


def test_max_preserves_whitespace_around_plus() -> None:
    assert minify("a{width:max(1rem + 2vw, 3rem)}") == "a{width:max(1rem + 2vw,3rem)}"


def test_nested_math_functions_preserve_operators() -> None:
    assert (
        minify("a{width:max(min(1rem + 2vw, 50%), calc(3rem + 1px))}")
        == "a{width:max(min(1rem + 2vw,50%),calc(3rem + 1px))}"
    )


def test_calc_preserves_whitespace() -> None:
    assert minify("a{width:calc(100% - 2rem)}") == "a{width:calc(100% - 2rem)}"


def test_calc_preserves_whitespace_after_var() -> None:
    assert minify("a{width:calc(var(--gap) + 1px)}") == "a{width:calc(var(--gap) + 1px)}"


def test_math_function_names_are_case_insensitive() -> None:
    assert (
        minify("a{font-size:CLAMP(1rem, 0.5rem + 2vw, 2rem)}")
        == "a{font-size:CLAMP(1rem,0.5rem + 2vw,2rem)}"
    )


def test_math_function_nested_in_unguarded_function_is_protected() -> None:
    assert (
        minify("a{grid-template-columns:repeat(auto-fill, minmax(min(10rem + 1vw, 100%), 1fr))}")
        == "a{grid-template-columns:repeat(auto-fill,minmax(min(10rem + 1vw,100%),1fr))}"
    )


def test_hsl_space_separated_syntax_preserved() -> None:
    assert minify("a{color:hsl(200deg 50% 40% / 80%)}") == "a{color:hsl(200deg 50% 40% / 80%)}"


def test_hsl_case_insensitive() -> None:
    assert minify("a{color:HSL(200deg 50% 40% / 80%)}") == "a{color:HSL(200deg 50% 40% / 80%)}"


def test_rgb_slash_alpha_preserved() -> None:
    assert minify("a{color:rgb(255 0 0 / 50%)}") == "a{color:rgb(255 0 0 / 50%)}"


def test_oklch_keeps_leading_zero_and_spacing() -> None:
    assert minify("a{color:oklch(70% 0.1 200 / 50%)}") == "a{color:oklch(70% 0.1 200 / 50%)}"


def test_hwb_percentages_are_not_stripped() -> None:
    assert minify("a{color:hwb(194 0% 0% / 50%)}") == "a{color:hwb(194 0% 0% / 50%)}"


def test_color_mix_preserved() -> None:
    assert (
        minify(":root{--pale:color-mix(in srgb, var(--accent) 9%, white)}")
        == ":root{--pale:color-mix(in srgb,var(--accent) 9%,white)}"
    )


def test_url_with_parentheses_is_untouched() -> None:
    assert minify("a{background:url(foo(bar).png)}") == "a{background:url(foo(bar).png)}"


def test_url_containing_math_function_is_untouched() -> None:
    assert (
        minify('a{background:url("x clamp( 1 , 2 ).png")}')
        == 'a{background:url("x clamp( 1 , 2 ).png")}'
    )


def test_quoted_string_containing_clamp_is_untouched() -> None:
    assert (
        minify('a::before{content:"clamp(1rem, 2rem + 1vw, 3rem)"}')
        == 'a::before{content:"clamp(1rem, 2rem + 1vw, 3rem)"}'
    )


def test_comment_containing_clamp_is_dropped() -> None:
    assert minify("/* clamp(1rem, 2 + 3, 4) */ a{color:red}") == "a{color:red}"


def test_guarded_call_is_condensed() -> None:
    assert (
        minify("a{font-size:clamp( 1rem , 0.5rem + 2vw , 2rem ) !important}")
        == "a{font-size:clamp(1rem,0.5rem + 2vw,2rem) !important}"
    )


def test_guarded_call_survives_inside_shorthand() -> None:
    assert (
        minify("a{padding:0 clamp(1rem, 2vw + 1rem, 3rem) 0}")
        == "a{padding:0 clamp(1rem,2vw + 1rem,3rem) 0}"
    )


def test_minification_still_shrinks_output() -> None:
    source = """
    /* header */
    .plym-header {
      display: flex;
      padding: 1.5rem 2.5rem;
      color: #FFFFFF;
      margin: 0px 0px 0px 0px;
    }

    .plym-content h2 {
      font-size: clamp(1.5rem, 1rem + 2vw, 2.5rem);
      margin: 3.25rem 0 0.9rem;
    }
    """
    result = minify(source)
    assert len(result) < len(source) * 0.7
    assert "\n" not in result
    assert "/* header */" not in result
    assert "clamp(1.5rem,1rem + 2vw,2.5rem)" in result


def test_reserved_guard_token_in_source_is_rejected() -> None:
    with pytest.raises(ValueError):
        minify("a{width:__PLYM_CSS_GUARD_0__}")


def test_unbalanced_math_function_is_rejected() -> None:
    with pytest.raises(ValueError):
        minify("a{width:clamp(1rem, 2rem}")


def test_unterminated_string_is_rejected() -> None:
    with pytest.raises(ValueError):
        minify('a::before{content:"oops}')


@pytest.fixture
def bundler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> "CssBundler":
    from plym.config.site import SiteConfig

    settings = importlib.import_module("plym.settings").settings
    monkeypatch.setattr(settings, "static_dir", tmp_path / "static")
    monkeypatch.setattr(settings, "build_dir", tmp_path / "build")
    monkeypatch.setattr(settings, "templates_dir", tmp_path / "templates")
    css_dir = tmp_path / "templates" / "default" / "css"
    css_dir.mkdir(parents=True)
    (css_dir / "components.css").write_text(".plym-content .admonition{padding:9px}")
    site = SiteConfig(name="T")
    site.prism.enabled = False
    return CssBundler(site)


def test_core_css_is_bundled_for_every_template(bundler: "CssBundler") -> None:
    css = bundler.build()
    assert ".admonition-title" in css
    assert ".tabbed-labels" in css
    assert ".plym-gallery" in css


def test_template_css_overrides_core_css(bundler: "CssBundler") -> None:
    css = bundler.build()
    assert css.index("padding:9px") > css.index(".admonition-title")


def test_core_css_only_depends_on_bundled_variables() -> None:
    import re

    guaranteed = {
        "--color-primary",
        "--color-secondary",
        "--color-accent",
        "--color-background",
        "--font-heading",
        "--font-body",
    }
    for path in sorted(CORE_CSS_DIR.glob("*.css")):
        source = path.read_text()
        declared = set(re.findall(r"(--[\w-]+)\s*:", source))
        referenced = set(re.findall(r"var\((--[\w-]+)", source))
        unresolved = referenced - guaranteed - declared
        assert not unresolved, f"{path.name} references template-local vars {unresolved}"

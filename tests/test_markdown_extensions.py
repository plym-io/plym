import pytest

from plym.exceptions.posts import TooManyTabsError
from plym.render.markdown_renderer import MAX_TABS, MarkdownRenderer


@pytest.fixture
def renderer() -> MarkdownRenderer:
    return MarkdownRenderer()


def _tabs(count: int) -> str:
    return "\n\n".join(f"/// tab | T{i}\nbody {i}\n///" for i in range(count))


def test_admonition_shorthand_emits_type_class(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render("/// tip | Pro tip\nbody\n///")
    assert 'class="admonition tip"' in html
    assert '<p class="admonition-title">Pro tip</p>' in html


def test_admonition_type_option_emits_type_class(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render("/// admonition | Careful\n    type: warning\n\nbody\n///")
    assert 'class="admonition warning"' in html


def test_admonition_without_title_uses_default_title(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render("/// note\nbody\n///")
    assert '<p class="admonition-title">Note</p>' in html


def test_admonition_body_renders_markdown(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render("/// note | T\nUse **bold** and [a link](/x).\n\n- one\n///")
    assert "<strong>bold</strong>" in html
    assert '<a href="/x"' in html
    assert "<li>one</li>" in html


def test_consecutive_tabs_group_into_one_set(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(_tabs(3))
    assert html.count("tabbed-set") == 1
    assert html.count("tabbed-block") == 3


def test_tabs_emit_radio_and_label_pairs(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(_tabs(2))
    assert 'name="__tabbed_1"' in html
    assert '<label for="__tabbed_1_1">T0</label>' in html
    assert '<label for="__tabbed_1_2">T1</label>' in html
    assert 'checked=""' in html


def test_tabs_use_alternate_style_layout(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(_tabs(2))
    assert "tabbed-alternate" in html
    assert html.count('class="tabbed-labels"') == 1
    assert html.count('class="tabbed-content"') == 1


def test_code_fence_inside_tab_keeps_language_class(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render('/// tab | Python\n```python\nprint("hi")\n```\n///')
    assert "language-python" in html


def test_tab_ids_are_stable_across_renders(renderer: MarkdownRenderer) -> None:
    first, _ = renderer.render(_tabs(2))
    second, _ = renderer.render(_tabs(2))
    assert first == second


def test_tab_set_at_limit_renders(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(_tabs(MAX_TABS))
    assert html.count("tabbed-block") == MAX_TABS


def test_tab_set_over_limit_is_rejected(renderer: MarkdownRenderer) -> None:
    with pytest.raises(TooManyTabsError) as excinfo:
        renderer.render(_tabs(MAX_TABS + 1))
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["code"] == "posts.too_many_tabs"


def test_gallery_still_renders_alongside_blocks(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render("/// note | T\nb\n///\n\n```gallery\n![a](/media/a.webp)\n```")
    assert 'class="plym-gallery"' in html
    assert 'class="admonition note"' in html

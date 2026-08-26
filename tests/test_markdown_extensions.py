import pytest

from plym.exceptions.posts import (
    EmptyTabSetError,
    MisplacedTabError,
    TabSetContentError,
    TooManyTabsError,
    UnclosedBlockError,
)
from plym.render.colon_blocks import MAX_TABS
from plym.render.markdown_renderer import MarkdownRenderer


@pytest.fixture
def renderer() -> MarkdownRenderer:
    return MarkdownRenderer()


def _tabs(count: int) -> str:
    body = "".join(f":::tab T{i}\nbody {i}\n:::\n" for i in range(count))
    return f":::tabs\n{body}:::"


def test_admonition_shorthand_emits_type_class(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(":::warning\nsome warning here\n:::")
    assert 'class="admonition warning"' in html
    assert "<p>some warning here</p>" in html


def test_admonition_without_title_uses_the_type_as_title(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(":::note\nsome note here\n:::")
    assert '<p class="admonition-title">Note</p>' in html


def test_admonition_takes_a_title_after_the_type(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(":::tip Pro tip\nbody\n:::")
    assert 'class="admonition tip"' in html
    assert '<p class="admonition-title">Pro tip</p>' in html


def test_admonition_body_renders_markdown(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(":::note\nUse **bold** and [a link](/x).\n\n- one\n:::")
    assert "<strong>bold</strong>" in html
    assert '<a href="/x"' in html
    assert "<li>one</li>" in html


def test_admonition_needs_no_blank_line_around_it(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render("intro\n:::note\nbody\n:::\nafter")
    assert "<p>intro</p>" in html
    assert 'class="admonition note"' in html
    assert "<p>after</p>" in html


def test_admonitions_nest(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(":::note Outer\n:::tip Inner\ndeep\n:::\n:::")
    assert html.index('class="admonition note"') < html.index('class="admonition tip"')
    assert html.count("admonition-title") == 2


def test_unknown_block_name_stays_literal(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(":::info\nhello\n:::")
    assert "admonition" not in html
    assert ":::info" in html


def test_colon_fence_inside_a_code_block_stays_literal(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render("```\n:::warning\nnot a block\n```")
    assert "admonition" not in html
    assert ":::warning" in html


def test_escaped_fence_stays_literal(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render("\\:::warning\nplain text\n\\:::")
    assert "admonition" not in html
    assert ":::warning" in html


def test_unclosed_block_is_rejected(renderer: MarkdownRenderer) -> None:
    with pytest.raises(UnclosedBlockError) as excinfo:
        renderer.render(":::warning\nno close here")
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["code"] == "posts.unclosed_block"


def test_tabs_group_into_one_set(renderer: MarkdownRenderer) -> None:
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
    html, _ = renderer.render(':::tabs\n:::tab Python\n```python\nprint("hi")\n```\n:::\n:::')
    assert "language-python" in html


def test_admonition_inside_tab_renders(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(":::tabs\n:::tab A\n:::warning\ncareful\n:::\n:::\n:::")
    assert html.count("tabbed-block") == 1
    assert 'class="admonition warning"' in html


def test_tab_ids_are_stable_across_renders(renderer: MarkdownRenderer) -> None:
    first, _ = renderer.render(_tabs(2))
    second, _ = renderer.render(_tabs(2))
    assert first == second


def test_separate_tab_sets_get_separate_radio_groups(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(f"{_tabs(2)}\n\n{_tabs(2)}")
    assert html.count("tabbed-set") == 2
    assert 'name="__tabbed_1"' in html
    assert 'name="__tabbed_2"' in html


def test_tab_set_at_limit_renders(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(_tabs(MAX_TABS))
    assert html.count("tabbed-block") == MAX_TABS


def test_tab_set_over_limit_is_rejected(renderer: MarkdownRenderer) -> None:
    with pytest.raises(TooManyTabsError) as excinfo:
        renderer.render(_tabs(MAX_TABS + 1))
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["code"] == "posts.too_many_tabs"


def test_tab_outside_a_tab_set_is_rejected(renderer: MarkdownRenderer) -> None:
    with pytest.raises(MisplacedTabError) as excinfo:
        renderer.render(":::tab Lonely\nbody\n:::")
    assert excinfo.value.detail["code"] == "posts.misplaced_tab"


def test_content_outside_a_tab_is_rejected(renderer: MarkdownRenderer) -> None:
    with pytest.raises(TabSetContentError) as excinfo:
        renderer.render(":::tabs\nstray\n:::tab A\nbody\n:::\n:::")
    assert excinfo.value.detail["code"] == "posts.tab_set_content"


def test_unnamed_tab_is_rejected(renderer: MarkdownRenderer) -> None:
    with pytest.raises(TabSetContentError):
        renderer.render(":::tabs\n:::tab\nbody\n:::\n:::")


def test_empty_tab_set_is_rejected(renderer: MarkdownRenderer) -> None:
    with pytest.raises(EmptyTabSetError) as excinfo:
        renderer.render(":::tabs\n:::")
    assert excinfo.value.detail["code"] == "posts.empty_tab_set"


def test_gallery_still_renders_alongside_blocks(renderer: MarkdownRenderer) -> None:
    html, _ = renderer.render(":::note\nb\n:::\n\n```gallery\n![a](/media/a.webp)\n```")
    assert 'class="plym-gallery"' in html
    assert 'class="admonition note"' in html

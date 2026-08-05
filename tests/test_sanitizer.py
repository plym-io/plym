import pytest

from plym.render.markdown_renderer import MarkdownRenderer
from plym.render.sanitizer import sanitize


@pytest.mark.parametrize(
    "payload",
    [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        '<a href="javascript:alert(1)">x</a>',
        "<iframe src=//evil.example></iframe>",
        '<object data="evil.swf"></object>',
        '<embed src="evil.swf">',
        "<style>body{display:none}</style>",
        '<form action="//evil.example"><input name="p"></form>',
        '<svg onload="alert(1)"></svg>',
        '<body onload="alert(1)">',
        '<div onmouseover="alert(1)">hover</div>',
        '<a href="data:text/html;base64,PHNjcmlwdD4=">x</a>',
    ],
)
def test_dangerous_markup_is_stripped(payload: str) -> None:
    out = sanitize(payload)
    assert "<script" not in out
    assert "javascript:" not in out
    assert "onerror" not in out
    assert "onload" not in out
    assert "onmouseover" not in out
    assert "<iframe" not in out
    assert "<object" not in out
    assert "<embed" not in out
    assert "<form" not in out


def test_markdown_render_sanitizes_raw_html() -> None:
    html, _ = MarkdownRenderer().render("Intro.\n\n<script>alert(1)</script>\n")
    assert "<script" not in html
    assert "Intro." in html


def test_attr_list_event_handler_is_stripped() -> None:
    renderer = MarkdownRenderer()
    html, _ = renderer.render('# Title {: onclick="alert(1)" }')
    assert "onclick" not in html
    assert "Title" in html

    html, _ = renderer.render('[link](http://example.com){: onclick="alert(1)" }')
    assert "onclick" not in html
    assert 'href="http://example.com"' in html


def test_attr_list_keeps_safe_attributes() -> None:
    html, _ = MarkdownRenderer().render("# Head {: .cls #myid }")
    assert 'class="cls"' in html
    assert 'id="myid"' in html


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        ('<pre><code class="language-python">x = 1</code></pre>', "language-python"),
        ('<h2 id="intro">Intro</h2>', 'id="intro"'),
        ('<input type="checkbox" disabled checked>', "checkbox"),
        ('<div class="plym-gallery"><img src="/media/a.webp" alt="a"></div>', "plym-gallery"),
        ('<input id="__tabbed_1_1" name="__tabbed_1" type="radio">', 'name="__tabbed_1"'),
        ('<label for="__tabbed_1_1">Python</label>', 'for="__tabbed_1_1"'),
        ('<div class="admonition tip"><p class="admonition-title">T</p></div>', "admonition-title"),
        ('<table><tr><td colspan="2">1</td></tr></table>', "colspan"),
        ('<img src="/media/a.webp" alt="a" loading="lazy" decoding="async">', "loading"),
        ('<a href="https://example.com">x</a>', "https://example.com"),
        ('<a href="#fn:1">1</a>', "#fn:1"),
    ],
)
def test_legitimate_markup_survives(markup: str, expected: str) -> None:
    assert expected in sanitize(markup)


def test_code_fence_survives_render() -> None:
    html, _ = MarkdownRenderer().render("```python\nprint('hi')\n```")
    assert "language-python" in html


def test_task_list_survives_render() -> None:
    html, _ = MarkdownRenderer().render("- [x] done\n- [ ] todo\n")
    assert 'type="checkbox"' in html


def test_external_links_get_noopener() -> None:
    assert "noopener" in sanitize('<a href="https://example.com">x</a>')

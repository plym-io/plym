from plym.render.excerpt import EXCERPT_LIMIT, derive_excerpt, resolve_excerpt


def test_an_authored_excerpt_is_returned_untouched() -> None:
    assert resolve_excerpt("Hand written", "# Title\n\nProse.") == "Hand written"


def test_a_blank_excerpt_falls_back_to_the_content() -> None:
    assert resolve_excerpt("   ", "Prose.") == "Prose."
    assert resolve_excerpt("", "Prose.") == "Prose."
    assert resolve_excerpt(None, "Prose.") == "Prose."


def test_content_without_prose_leaves_the_excerpt_empty() -> None:
    assert resolve_excerpt(None, "") is None
    assert resolve_excerpt(None, "# Title\n\n```\ncode only\n```") is None


def test_headings_are_not_prose() -> None:
    assert derive_excerpt("# Title\n\nThe body.") == "The body."
    assert derive_excerpt("###### Deep\n\nThe body.") == "The body."
    assert derive_excerpt("Title\n=====\n\nThe body.") == "The body."
    assert derive_excerpt("Title\n-----\n\nThe body.") == "The body."


def test_fenced_blocks_are_skipped_including_custom_fences() -> None:
    assert derive_excerpt("```python\nprint(1)\n```\n\nAfter.") == "After."
    assert derive_excerpt("~~~\nprint(1)\n~~~\n\nAfter.") == "After."
    assert derive_excerpt("```gallery\n![a](/a.png)\n```\n\nAfter.") == "After."


def test_a_fence_is_closed_only_by_its_own_marker() -> None:
    content = "````\n```\nstill code\n````\n\nAfter."
    assert derive_excerpt(content) == "After."


def test_indented_code_blocks_are_skipped() -> None:
    assert derive_excerpt('    indented = "code"\n\nAfter.') == "After."


def test_colon_block_delimiters_drop_but_their_bodies_are_prose() -> None:
    assert derive_excerpt(":::note Heads up\nInside the note.\n:::") == "Inside the note."


def test_tables_thematic_breaks_and_raw_html_are_skipped() -> None:
    assert derive_excerpt("| a | b |\n| - | - |\n| 1 | 2 |\n\nAfter.") == "After."
    assert derive_excerpt("---\n\nAfter.") == "After."
    assert derive_excerpt("***\n\nAfter.") == "After."
    assert derive_excerpt('<div class="hero">\n\nAfter.') == "After."


def test_link_definitions_and_footnote_definitions_are_skipped() -> None:
    content = "Fast[^1] and small.\n\n[^1]: measured\n[docs]: https://plym.io/docs"
    assert derive_excerpt(content) == "Fast and small."


def test_inline_markup_is_reduced_to_its_text() -> None:
    content = "Read the [docs](https://plym.io) for **bold**, `code`, _em_ and ~~struck~~ claims."
    assert derive_excerpt(content) == "Read the docs for bold, code, em and struck claims."


def test_reference_links_keep_their_label() -> None:
    assert derive_excerpt("See the [handbook][hb] first.") == "See the handbook first."


def test_backslash_escapes_are_unescaped() -> None:
    assert derive_excerpt(r"A literal \* and a \[bracket\].") == "A literal * and a [bracket]."


def test_images_contribute_nothing() -> None:
    assert derive_excerpt("![cover](/media/cover.png)\n\nAfter.") == "After."


def test_list_and_quote_markers_are_stripped() -> None:
    assert derive_excerpt("- **Fast**: ships static HTML") == "Fast: ships static HTML"
    assert derive_excerpt("1. First step") == "First step"
    assert derive_excerpt("> Quoted prose.") == "Quoted prose."


def test_paragraphs_are_joined_until_the_limit_is_reached() -> None:
    content = "First line.\n\nSecond line.\n\nThird line."
    assert derive_excerpt(content) == "First line. Second line. Third line."


def test_long_content_is_cut_at_a_word_boundary_within_the_limit() -> None:
    word = "alpha "
    excerpt = derive_excerpt(word * 60)
    assert len(excerpt) <= EXCERPT_LIMIT
    assert excerpt.endswith("…")
    assert "alph…" not in excerpt


def test_content_at_the_limit_is_not_truncated() -> None:
    content = "x" * EXCERPT_LIMIT
    assert derive_excerpt(content) == content

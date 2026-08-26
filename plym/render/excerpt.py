import re
from collections.abc import Iterator

EXCERPT_LIMIT = 140

_FENCE = re.compile(r"^ {0,3}(?P<mark>`{3,}|~{3,})")
_ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")
_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(?:=+|-{2,})[ \t]*$")
_THEMATIC_BREAK = re.compile(r"^ {0,3}(?:[*_-][ \t]*){3,}$")
_COLON_DELIMITER = re.compile(r"^ {0,3}:::")
_REFERENCE_DEFINITION = re.compile(r"^ {0,3}\[[^\]]+\]:")
_HTML_LINE = re.compile(r"^ {0,3}<")

_STRUCTURAL = (
    _ATX_HEADING,
    _SETEXT_UNDERLINE,
    _THEMATIC_BREAK,
    _COLON_DELIMITER,
    _REFERENCE_DEFINITION,
    _HTML_LINE,
)

_LEADING_MARKERS = re.compile(r"^[ \t]*(?:>[ \t]*|[-*+][ \t]+|\d+[.)][ \t]+)+")

_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_FOOTNOTE_REFERENCE = re.compile(r"\[\^[^\]]*\]")
_INLINE_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_REFERENCE_LINK = re.compile(r"\[([^\]]*)\]\[[^\]]*\]")
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_ASTERISK_EMPHASIS = re.compile(r"(\*{1,3}|~{1,2})(\S(?:.*?\S)?)\1")
_UNDERSCORE_EMPHASIS = re.compile(r"(?<![\w\\])(_{1,3})(\S(?:.*?\S)?)\1(?!\w)")
_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>~|])")

_TRAILING_PUNCTUATION = " \t,;:.!?-–—"


def _is_indented(line: str) -> bool:
    return line.startswith("    ") or line.startswith("\t")


def _closes_fence(fence: str, line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(fence) and set(stripped) == {fence[0]}


def _is_structural(line: str) -> bool:
    return "|" in line or any(pattern.match(line) for pattern in _STRUCTURAL)


def _underlined_by_setext(lines: list[str], index: int) -> bool:
    following = index + 1
    return following < len(lines) and _SETEXT_UNDERLINE.match(lines[following]) is not None


def _prose_lines(content: str) -> Iterator[str]:
    lines = content.splitlines()
    fence: str | None = None
    indented_code = False
    after_blank = True
    for index, line in enumerate(lines):
        if fence is not None:
            if _closes_fence(fence, line):
                fence = None
            continue
        if not line.strip():
            indented_code = False
            after_blank = True
            continue
        opening = _FENCE.match(line)
        if opening is not None:
            fence = opening.group("mark")
            after_blank = False
            continue
        if _is_indented(line) and (indented_code or after_blank):
            indented_code = True
            after_blank = False
            continue
        indented_code = False
        after_blank = False
        if _is_structural(line) or _underlined_by_setext(lines, index):
            continue
        text = _LEADING_MARKERS.sub("", line).strip()
        if text:
            yield text


def _inline_text(line: str) -> str:
    text = _IMAGE.sub("", line)
    text = _FOOTNOTE_REFERENCE.sub("", text)
    text = _INLINE_LINK.sub(r"\1", text)
    text = _REFERENCE_LINK.sub(r"\1", text)
    text = _CODE_SPAN.sub(r"\2", text)
    text = _HTML_TAG.sub("", text)
    text = _ASTERISK_EMPHASIS.sub(r"\2", text)
    text = _UNDERSCORE_EMPHASIS.sub(r"\2", text)
    text = _ESCAPE.sub(r"\1", text)
    return " ".join(text.split())


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit - 1]
    boundary = head.rfind(" ")
    if boundary > 0:
        head = head[:boundary]
    return head.rstrip(_TRAILING_PUNCTUATION) + "…"


def derive_excerpt(content: str, limit: int = EXCERPT_LIMIT) -> str:
    collected: list[str] = []
    length = 0
    for line in _prose_lines(content):
        text = _inline_text(line)
        if not text:
            continue
        collected.append(text)
        length += len(text) + 1
        if length > limit:
            break
    return _truncate(" ".join(collected), limit)


def resolve_excerpt(excerpt: str | None, content: str) -> str | None:
    if excerpt and excerpt.strip():
        return excerpt
    return derive_excerpt(content) or None

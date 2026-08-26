import re
from dataclasses import dataclass
from xml.etree.ElementTree import Element, SubElement

import markdown
from markdown.blockparser import BlockParser
from markdown.blockprocessors import BlockProcessor
from markdown.extensions import Extension

from plym.exceptions.posts import (
    EmptyTabSetError,
    MisplacedTabError,
    TabSetContentError,
    TooManyTabsError,
    UnclosedBlockError,
)

ADMONITION_TYPES = frozenset(
    {
        "note",
        "attention",
        "caution",
        "danger",
        "error",
        "tip",
        "hint",
        "warning",
        "important",
    }
)

TABS = "tabs"
TAB = "tab"
MAX_TABS = 6

_BLOCK_NAMES = ADMONITION_TYPES | {TABS, TAB}

_OPEN = re.compile(r"^ {0,3}:::[ ]*(?P<name>[A-Za-z][\w-]*)[ ]*(?P<title>.*?)[ ]*$")
_CLOSE = re.compile(r"^ {0,3}:::[ ]*$")


@dataclass(frozen=True)
class Opener:
    line: int
    name: str
    title: str


@dataclass(frozen=True)
class TabSection:
    title: str
    body: str


def _opener_at(lines: list[str], index: int) -> Opener | None:
    match = _OPEN.match(lines[index])
    if match is None:
        return None
    return Opener(index, match.group("name").lower(), match.group("title"))


def _find_opener(lines: list[str]) -> Opener | None:
    for index in range(len(lines)):
        opener = _opener_at(lines, index)
        if opener is not None and opener.name in _BLOCK_NAMES:
            return opener
    return None


def _find_close(lines: list[str], start: int) -> int | None:
    depth = 1
    for index in range(start, len(lines)):
        if _CLOSE.match(lines[index]):
            depth -= 1
            if depth == 0:
                return index
        elif _OPEN.match(lines[index]):
            depth += 1
    return None


def _split_tabs(body: str) -> list[TabSection]:
    lines = body.split("\n")
    sections: list[TabSection] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        opener = _opener_at(lines, index)
        if opener is None or opener.name != TAB or not opener.title:
            raise TabSetContentError()
        close = _find_close(lines, index + 1)
        if close is None:
            raise UnclosedBlockError(TAB)
        sections.append(TabSection(opener.title, "\n".join(lines[index + 1 : close])))
        index = close + 1
    return sections


class TabGroups:
    def __init__(self) -> None:
        self._count = 0

    def next(self) -> int:
        self._count += 1
        return self._count

    def reset(self) -> None:
        self._count = 0


class ColonBlockProcessor(BlockProcessor):  # type: ignore[misc]
    def __init__(self, parser: BlockParser, groups: TabGroups) -> None:
        super().__init__(parser)
        self._groups = groups

    def test(self, parent: Element, block: str) -> bool:
        return _find_opener(block.split("\n")) is not None

    def run(self, parent: Element, blocks: list[str]) -> bool | None:
        lines = "\n\n".join(blocks).split("\n")
        opener = _find_opener(lines)
        if opener is None:
            return False
        if opener.name == TAB:
            raise MisplacedTabError()
        close = _find_close(lines, opener.line + 1)
        if close is None:
            raise UnclosedBlockError(opener.name)

        blocks.clear()
        blocks.extend("\n".join(lines[close + 1 :]).split("\n\n"))

        if opener.line:
            self.parser.parseChunk(parent, "\n".join(lines[: opener.line]))
        body = "\n".join(lines[opener.line + 1 : close])
        if opener.name == TABS:
            self._tabs(parent, body)
        else:
            self._admonition(parent, opener, body)
        return None

    def _admonition(self, parent: Element, opener: Opener, body: str) -> None:
        el = SubElement(parent, "div", {"class": f"admonition {opener.name}"})
        title = SubElement(el, "p", {"class": "admonition-title"})
        title.text = opener.title or opener.name.title()
        self.parser.parseChunk(el, body)

    def _tabs(self, parent: Element, body: str) -> None:
        sections = _split_tabs(body)
        if not sections:
            raise EmptyTabSetError()
        if len(sections) > MAX_TABS:
            raise TooManyTabsError(len(sections), MAX_TABS)

        group = self._groups.next()
        el = SubElement(parent, "div", {"class": "tabbed-set tabbed-alternate"})
        labels = Element("div", {"class": "tabbed-labels"})
        content = Element("div", {"class": "tabbed-content"})
        for position, section in enumerate(sections, start=1):
            tab_id = f"__tabbed_{group}_{position}"
            attributes = {"name": f"__tabbed_{group}", "type": "radio", "id": tab_id}
            if position == 1:
                attributes["checked"] = "checked"
            SubElement(el, "input", attributes)
            label = SubElement(labels, "label", {"for": tab_id})
            label.text = section.title
            block = SubElement(content, "div", {"class": "tabbed-block"})
            self.parser.parseChunk(block, section.body)
        el.append(labels)
        el.append(content)


class ColonBlockExtension(Extension):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self._groups = TabGroups()

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.registerExtension(self)
        md.ESCAPED_CHARS.append(":")
        md.parser.blockprocessors.register(
            ColonBlockProcessor(md.parser, self._groups), "plym_colon_blocks", 89.9
        )

    def reset(self) -> None:
        self._groups.reset()

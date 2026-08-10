import html
import re
from typing import Any
from xml.etree.ElementTree import Element

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from plym.render.colon_blocks import ColonBlockExtension
from plym.render.sanitizer import sanitize

_GALLERY_IMAGE = re.compile(r"!\[(?P<alt>.*?)\]\((?P<src>\S+?)(?:\s+\"[^\"]*\")?\)")


class LazyImageTreeprocessor(Treeprocessor):  # type: ignore[misc]
    def run(self, root: Element) -> None:
        for img in root.iter("img"):
            img.set("loading", "lazy")
            img.set("decoding", "async")


class LazyImageExtension(Extension):  # type: ignore[misc]
    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.treeprocessors.register(LazyImageTreeprocessor(md), "plym_lazy_images", 5)


def _gallery_image(line: str) -> str:
    match = _GALLERY_IMAGE.search(line)
    alt, src = (match.group("alt"), match.group("src")) if match else ("", line)
    return (
        f'<img src="{html.escape(src, quote=True)}" '
        f'alt="{html.escape(alt, quote=True)}" '
        f'loading="lazy" decoding="async">'
    )


def render_gallery(
    source: str,
    language: str,
    css_class: str,
    options: dict[str, Any] | None,
    md: markdown.Markdown,
    **kwargs: Any,
) -> str:
    images = "".join(_gallery_image(line.strip()) for line in source.splitlines() if line.strip())
    return f'<div class="{css_class}">{images}</div>'


class MarkdownRenderer:
    def __init__(self) -> None:
        self._md = markdown.Markdown(
            extensions=[
                "extra",
                "toc",
                "tables",
                "fenced_code",
                "footnotes",
                "sane_lists",
                "pymdownx.tilde",
                "pymdownx.tasklist",
                "pymdownx.highlight",
                "pymdownx.superfences",
                LazyImageExtension(),
                ColonBlockExtension(),
            ],
            extension_configs={
                "toc": {
                    "anchorlink": True,
                    "toc_depth": "2-4",
                },
                # Highlighting happens client-side via Prism. Pygments is not a
                # declared dependency but arrives transitively, and when present
                # superfences silently switches to Pygments' `.nt`/`.k` markup,
                # which the shipped Prism theme has no rules for.
                "pymdownx.highlight": {
                    "use_pygments": False,
                },
                "pymdownx.superfences": {
                    "custom_fences": [
                        {
                            "name": "gallery",
                            "class": "plym-gallery",
                            "format": render_gallery,
                        }
                    ]
                },
            },
            output_format="html",
        )

    def render(self, content: str) -> tuple[str, list[dict[str, Any]]]:
        self._md.reset()
        html = sanitize(self._md.convert(content))
        toc = getattr(self._md, "toc_tokens", None) or []
        return html, toc

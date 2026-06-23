import html
import re

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

_GALLERY_IMAGE = re.compile(r"!\[(?P<alt>.*?)\]\((?P<src>\S+?)(?:\s+\"[^\"]*\")?\)")


class LazyImageTreeprocessor(Treeprocessor):
    def run(self, root):
        for img in root.iter("img"):
            img.set("loading", "lazy")
            img.set("decoding", "async")


class LazyImageExtension(Extension):
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


def render_gallery(source: str, language, css_class: str, options, md, **kwargs) -> str:
    images = "".join(
        _gallery_image(line.strip()) for line in source.splitlines() if line.strip()
    )
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
                "pymdownx.superfences",
                LazyImageExtension(),
            ],
            extension_configs={
                "toc": {
                    "anchorlink": True,
                    "toc_depth": "2-4",
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
            output_format="html5",
        )

    def render(self, content: str) -> tuple[str, list[dict]]:
        self._md.reset()
        html = self._md.convert(content)
        toc = getattr(self._md, "toc_tokens", None) or []
        return html, toc

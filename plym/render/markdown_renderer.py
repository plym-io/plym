import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor


class LazyImageTreeprocessor(Treeprocessor):
    def run(self, root):
        for img in root.iter("img"):
            img.set("loading", "lazy")
            img.set("decoding", "async")


class LazyImageExtension(Extension):
    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.treeprocessors.register(LazyImageTreeprocessor(md), "plym_lazy_images", 5)


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
                }
            },
            output_format="html5",
        )

    def render(self, content: str) -> tuple[str, list[dict]]:
        self._md.reset()
        html = self._md.convert(content)
        toc = getattr(self._md, "toc_tokens", None) or []
        return html, toc

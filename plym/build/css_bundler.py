import re
from pathlib import Path

import csscompressor

from plym.config.site import ColorsConfig, FontsConfig, SiteConfig
from plym.settings import settings

_MATH_FUNCTIONS = frozenset(
    {
        "calc",
        "min",
        "max",
        "clamp",
        "round",
        "mod",
        "rem",
        "abs",
        "sign",
        "hypot",
        "pow",
        "sqrt",
        "log",
        "exp",
    }
)

_COLOR_FUNCTIONS = frozenset(
    {
        "rgb",
        "rgba",
        "hsl",
        "hsla",
        "hwb",
        "lab",
        "lch",
        "oklab",
        "oklch",
        "color",
        "color-mix",
    }
)

_GUARDED_FUNCTIONS = _MATH_FUNCTIONS | _COLOR_FUNCTIONS

_TOKEN_FORMAT = "__PLYM_CSS_GUARD_{0}__"
_TOKEN_RE = re.compile(r"__PLYM_CSS_GUARD_(\d+)__")
_SCAN_RE = re.compile(r"/\*|[\"']|([-\w]+)\s*\(")
_WS_RUN_RE = re.compile(r"\s+")
_WS_AFTER_OPEN_RE = re.compile(r"\(\s")
_WS_BEFORE_CLOSE_RE = re.compile(r"\s\)")
_WS_AROUND_COMMA_RE = re.compile(r"\s*,\s*")


def _end_of_string(css: str, start: int) -> int:
    quote = css[start]
    i = start + 1
    while i < len(css):
        if css[i] == "\\":
            i += 2
            continue
        if css[i] == quote:
            return i + 1
        i += 1
    raise ValueError(f"unterminated css string starting at offset {start}")


def _end_of_call(css: str, open_idx: int) -> int:
    depth = 0
    i = open_idx
    while i < len(css):
        char = css[i]
        if char == "\\":
            i += 2
            continue
        if char in "\"'":
            i = _end_of_string(css, i)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError(f"unbalanced css function starting at offset {open_idx}")


def _end_of_comment(css: str, start: int) -> int:
    end = css.find("*/", start + 2)
    return len(css) if end < 0 else end + 2


def _condense(fragment: str) -> str:
    fragment = _WS_RUN_RE.sub(" ", fragment)
    fragment = _WS_AFTER_OPEN_RE.sub("(", fragment)
    fragment = _WS_BEFORE_CLOSE_RE.sub(")", fragment)
    return _WS_AROUND_COMMA_RE.sub(",", fragment)


class _FunctionGuard:
    def __init__(self) -> None:
        self._fragments: list[str] = []

    def mask(self, css: str) -> str:
        if _TOKEN_RE.search(css):
            raise ValueError("css already contains a plym guard token")
        out: list[str] = []
        pos = 0
        while (match := _SCAN_RE.search(css, pos)) is not None:
            out.append(css[pos : match.start()])
            pos = self._emit(css, match, out)
        out.append(css[pos:])
        return "".join(out)

    def _emit(self, css: str, match: re.Match[str], out: list[str]) -> int:
        start = match.start()
        name = match.group(1)
        if name is None:
            end = _end_of_comment(css, start) if css[start] == "/" else _end_of_string(css, start)
            out.append(css[start:end])
            return end
        paren = match.end() - 1
        lowered = name.lower()
        if lowered in _GUARDED_FUNCTIONS:
            end = _end_of_call(css, paren)
            out.append(self._store(name + _condense(css[paren:end])))
            return end
        if lowered == "url":
            end = _end_of_call(css, paren)
            out.append(css[start:end])
            return end
        out.append(css[start : match.end()])
        return match.end()

    def unmask(self, css: str) -> str:
        return _TOKEN_RE.sub(lambda m: self._fragments[int(m.group(1))], css)

    def _store(self, fragment: str) -> str:
        self._fragments.append(fragment)
        return _TOKEN_FORMAT.format(len(self._fragments) - 1)


def minify(css: str) -> str:
    guard = _FunctionGuard()
    return guard.unmask(csscompressor.compress(guard.mask(css)))


class CssBundler:
    def __init__(self, site: SiteConfig) -> None:
        self._site = site

    def _colors_vars(self, colors: ColorsConfig) -> str:
        return (
            ":root{"
            f"--color-primary:{colors.primary};"
            f"--color-secondary:{colors.secondary};"
            f"--color-accent:{colors.accent};"
            f"--color-background:{colors.background};"
            "}"
        )

    def _fonts_vars(self, fonts: FontsConfig) -> str:
        return f":root{{--font-heading:'{fonts.heading}';--font-body:'{fonts.body}';}}"

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _template_css(self, template: str) -> str:
        css_dir = settings.templates_dir / template / "css"
        if not css_dir.exists():
            return ""
        return "\n".join(self._read(p) for p in sorted(css_dir.glob("*.css")))

    def build(self) -> str:
        fonts = self._read(settings.static_dir / "fonts.css")
        prism = self._read(settings.static_dir / "prism.css") if self._site.prism.enabled else ""
        template = self._template_css(self._site.template)
        combined = "\n".join(
            chunk
            for chunk in (
                self._colors_vars(self._site.colors),
                self._fonts_vars(self._site.fonts),
                fonts,
                prism,
                template,
            )
            if chunk
        )
        return minify(combined)

    def prism_js(self) -> str:
        if not self._site.prism.enabled:
            return ""
        return self._read(settings.static_dir / "prism.js")

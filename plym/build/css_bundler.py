from pathlib import Path

import csscompressor

from plym.config.site import ColorsConfig, FontsConfig, SiteConfig
from plym.settings import settings


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
        return (
            ":root{"
            f"--font-heading:'{fonts.heading}';"
            f"--font-body:'{fonts.body}';"
            "}"
        )

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _template_css(self, template: str) -> str:
        css_dir = settings.templates_dir / template / "css"
        if not css_dir.exists():
            return ""
        return "\n".join(
            self._read(p) for p in sorted(css_dir.glob("*.css"))
        )

    def build(self) -> str:
        fonts = self._read(settings.static_dir / "fonts.css")
        prism = self._read(settings.static_dir / "prism.css") if self._site.prism.enabled else ""
        template = self._template_css(self._site.template)
        combined = "\n".join(
            chunk for chunk in (
                self._colors_vars(self._site.colors),
                self._fonts_vars(self._site.fonts),
                fonts,
                prism,
                template,
            ) if chunk
        )
        return csscompressor.compress(combined)

    def prism_js(self) -> str:
        if not self._site.prism.enabled:
            return ""
        return self._read(settings.static_dir / "prism.js")

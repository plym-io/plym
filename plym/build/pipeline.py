import logging

from plym.build.css_bundler import CssBundler
from plym.build.font_downloader import WebFontDownloader
from plym.build.prism_downloader import PrismJsDownloader
from plym.config.site import SiteConfig

log = logging.getLogger("plym.build")


class BuildArtifacts:
    def __init__(self, css: str, prism_js: str) -> None:
        self.css = css
        self.prism_js = prism_js


async def run_build(site: SiteConfig) -> BuildArtifacts:
    try:
        await WebFontDownloader(site).download()
    except Exception as exc:
        log.warning("font download failed: %s — continuing without webfonts", exc)

    try:
        await PrismJsDownloader(site.prism).download()
    except Exception as exc:
        log.warning("prism download failed: %s — continuing without prism", exc)

    bundler = CssBundler(site)
    return BuildArtifacts(css=bundler.build(), prism_js=bundler.prism_js())

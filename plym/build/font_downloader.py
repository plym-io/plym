import asyncio
import hashlib
import re
from urllib.parse import parse_qs, quote, urlparse

import aiofiles
import aiohttp

from plym.build.constants import BASE_URL, HTTP_TIMEOUT, TEXT, USER_AGENT
from plym.config.site import SiteConfig
from plym.settings import settings

_HASH_LEN = 8

# Google names font payloads by skey, which identifies family+variant only: the
# same skey serves different bytes whenever the subset text, or the font itself,
# changes. Filenames must therefore carry a content hash, or long-lived caches
# serve stale fonts under an unchanged URL.
_FONT_MAGICS = {
    b"wOF2": "woff2",
    b"wOFF": "woff",
    b"OTTO": "otf",
    b"\x00\x01\x00\x00": "ttf",
}


class UnrecognizedFontError(ValueError):
    def __init__(self, url: str, magic: bytes) -> None:
        super().__init__(f"unrecognized font payload from {url} (magic {magic!r})")


def _extension(url: str, payload: bytes) -> str:
    for magic, extension in _FONT_MAGICS.items():
        if payload.startswith(magic):
            return extension
    raise UnrecognizedFontError(url, payload[:4])


class WebFontDownloader:
    def __init__(self, site: SiteConfig) -> None:
        self._heading = site.fonts.heading
        self._body = site.fonts.body
        self._prefix = site.blog_prefix

    def _url(self) -> str:
        return (
            f"{BASE_URL}?family={self._heading}:wght@600;900&family={self._body}"
            f"&display=swap&text={quote(TEXT)}"
        )

    @staticmethod
    async def _fetch(session: aiohttp.ClientSession, url: str) -> bytes:
        response = await session.get(url)
        response.raise_for_status()
        return await response.read()

    @staticmethod
    def _filename(url: str, payload: bytes) -> str:
        skey = parse_qs(urlparse(url).query).get("skey")
        stem = skey[0] if skey else urlparse(url).path.rsplit("/", 1)[-1].partition(".")[0]
        digest = hashlib.sha256(payload).hexdigest()[:_HASH_LEN]
        return f"{stem}-{digest}.{_extension(url, payload)}"

    @staticmethod
    def _prune(kept: set[str]) -> None:
        for stale in settings.fonts_dir.iterdir():
            if stale.is_file() and stale.name not in kept:
                stale.unlink()

    async def download(self) -> str:
        async with aiohttp.ClientSession(
            timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as session:
            response = await session.get(self._url())
            response.raise_for_status()
            css = await response.text()

            urls = list(dict.fromkeys(re.findall(r"url\(['\"]?(.*?)['\"]?\)", css)))
            payloads = await asyncio.gather(*(self._fetch(session, url) for url in urls))

        kept: set[str] = set()
        for url, font_bytes in zip(urls, payloads, strict=True):
            filename = self._filename(url, font_bytes)
            kept.add(filename)
            async with aiofiles.open(settings.fonts_dir / filename, "wb") as f:
                await f.write(font_bytes)
            css = css.replace(url, f"{self._prefix}/webfonts/{filename}")
        self._prune(kept)

        output = settings.build_dir / "fonts.css"
        async with aiofiles.open(output, "w", encoding="utf-8") as f:
            await f.write(css)
        return css

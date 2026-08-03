import asyncio
import re
from urllib.parse import parse_qs, quote, urlparse

import aiofiles
import aiohttp

from plym.build.constants import BASE_URL, HTTP_TIMEOUT, TEXT, USER_AGENT
from plym.config.site import SiteConfig
from plym.settings import settings


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
    def _filename(url: str) -> str:
        skey = parse_qs(urlparse(url).query).get("skey")
        return skey[0] if skey else url.rsplit("/", 1)[-1]

    async def download(self) -> str:
        async with aiohttp.ClientSession(
            timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as session:
            response = await session.get(self._url())
            response.raise_for_status()
            css = await response.text()

            urls = list(dict.fromkeys(re.findall(r"url\(['\"]?(.*?)['\"]?\)", css)))
            payloads = await asyncio.gather(*(self._fetch(session, url) for url in urls))

        for url, font_bytes in zip(urls, payloads, strict=True):
            filename = self._filename(url)
            async with aiofiles.open(settings.fonts_dir / filename, "wb") as f:
                await f.write(font_bytes)
            css = css.replace(url, f"{self._prefix}/webfonts/{filename}")

        output = settings.static_dir / "fonts.css"
        async with aiofiles.open(output, "w", encoding="utf-8") as f:
            await f.write(css)
        return css

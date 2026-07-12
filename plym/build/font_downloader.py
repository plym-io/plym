import re
from urllib.parse import parse_qs, quote, urlparse

import aiofiles
import aiohttp

from plym.build.constants import BASE_URL, TEXT, USER_AGENT
from plym.config.site import SiteConfig
from plym.settings import settings


class WebFontDownloader:
    def __init__(self, site: SiteConfig) -> None:
        self._heading = site.fonts.heading
        self._body = site.fonts.body
        self._base = site.public_blog_url()

    def _url(self) -> str:
        return (
            f"{BASE_URL}?family={self._heading}:wght@600;900&family={self._body}"
            f"&display=swap&text={quote(TEXT)}"
        )

    async def download(self) -> str:
        async with aiohttp.ClientSession() as session:
            response = await session.get(self._url(), headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            css = await response.text()

            for url in re.findall(r"url\(['\"]?(.*?)['\"]?\)", css):
                font_bytes = await (await session.get(url)).read()
                skey = parse_qs(urlparse(url).query).get("skey")
                filename = skey[0] if skey else url.rsplit("/", 1)[-1]
                target = settings.fonts_dir / filename
                async with aiofiles.open(target, "wb") as f:
                    await f.write(font_bytes)
                css = css.replace(url, f"{self._base}/webfonts/{filename}")

        output = settings.static_dir / "fonts.css"
        async with aiofiles.open(output, "w", encoding="utf-8") as f:
            await f.write(css)
        return css

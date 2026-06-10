import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import aiofiles
import aiohttp

from plym.build.constants import USER_AGENT
from plym.config.site import SiteConfig
from plym.settings import settings

_DEFAULT_MEDIA = {"favicon": "image/x-icon", "logo": "image/webp"}


class SiteAsset:
    def __init__(self, web_path: str, file_path: Path, media_type: str) -> None:
        self.web_path = web_path
        self.file_path = file_path
        self.media_type = media_type


class SiteAssets:
    def __init__(self, favicon: SiteAsset | None, logo: SiteAsset | None) -> None:
        self.favicon = favicon
        self.logo = logo


class AssetDownloader:
    def __init__(self, site: SiteConfig) -> None:
        self._site = site

    async def download(self) -> SiteAssets:
        prefix = self._site.blog_prefix
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            favicon = await self._fetch(session, self._site.favicon, "favicon", f"{prefix}/favicon.ico")
            logo = await self._fetch(session, self._site.logo, "logo", f"{prefix}/logo.webp")
        return SiteAssets(favicon=favicon, logo=logo)

    async def _fetch(
        self,
        session: aiohttp.ClientSession,
        source: str | None,
        stem: str,
        web_path: str,
    ) -> SiteAsset | None:
        if not source or not source.startswith(("http://", "https://")):
            return None
        response = await session.get(source)
        response.raise_for_status()
        data = await response.read()
        media_type = self._media_type(source, response, stem)
        ext = mimetypes.guess_extension(media_type) or Path(urlparse(source).path).suffix
        target = settings.static_dir / f"{stem}{ext}"
        async with aiofiles.open(target, "wb") as f:
            await f.write(data)
        return SiteAsset(web_path=web_path, file_path=target, media_type=media_type)

    @staticmethod
    def _media_type(source: str, response: aiohttp.ClientResponse, stem: str) -> str:
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type.startswith("image/"):
            return content_type
        guessed, _ = mimetypes.guess_type(urlparse(source).path)
        return guessed or _DEFAULT_MEDIA[stem]

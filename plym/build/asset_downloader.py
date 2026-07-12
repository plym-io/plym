import hashlib
import io

import aiofiles
import aiohttp
from PIL import Image, UnidentifiedImageError

from plym.build.constants import USER_AGENT
from plym.config.site import SiteConfig
from plym.settings import settings

_HASH_LEN = 8


class SiteAsset:
    def __init__(self, web_path: str) -> None:
        self.web_path = web_path


class SiteAssets:
    def __init__(self, favicon: SiteAsset | None, logo: SiteAsset | None) -> None:
        self.favicon = favicon
        self.logo = logo


class AssetDownloader:
    def __init__(self, site: SiteConfig) -> None:
        self._site = site

    async def download(self) -> SiteAssets:
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            favicon = await self._favicon(session, self._site.favicon)
            logo = await self._logo(session, self._site.logo)
        return SiteAssets(favicon=favicon, logo=logo)

    async def _favicon(
        self, session: aiohttp.ClientSession, source: str | None
    ) -> SiteAsset | None:
        data = await self._download(session, source)
        if data is None:
            return None
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "ICO":
                    return None
        except (UnidentifiedImageError, OSError):
            return None
        return await self._store(data, "favicon", "ico")

    def _web_path(self, filename: str) -> str:
        return f"{self._site.public_blog_url()}/static/{filename}"

    async def _logo(self, session: aiohttp.ClientSession, source: str | None) -> SiteAsset | None:
        data = await self._download(session, source)
        if data is None:
            return None
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
                buf = io.BytesIO()
                image.save(buf, format="WEBP", quality=82, method=6)
        except (UnidentifiedImageError, OSError):
            return None
        return await self._store(buf.getvalue(), "logo", "webp")

    @staticmethod
    async def _download(session: aiohttp.ClientSession, source: str | None) -> bytes | None:
        if not source or not source.startswith(("http://", "https://")):
            return None
        response = await session.get(source)
        response.raise_for_status()
        return await response.read()

    async def _store(self, data: bytes, stem: str, ext: str) -> SiteAsset:
        digest = hashlib.sha256(data).hexdigest()[:_HASH_LEN]
        filename = f"{stem}-{digest}.{ext}"
        for stale in settings.static_dir.glob(f"{stem}-*.{ext}"):
            if stale.name != filename:
                stale.unlink()
        async with aiofiles.open(settings.static_dir / filename, "wb") as f:
            await f.write(data)
        return SiteAsset(web_path=self._web_path(filename))

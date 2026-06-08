import aiofiles
import aiohttp

from plym.build.constants import PRISM_COMPONENTS, PRISM_THEMES
from plym.config.site import PrismConfig
from plym.settings import settings


class PrismJsDownloader:
    def __init__(self, config: PrismConfig) -> None:
        self._config = config

    @staticmethod
    def _language_url(language: str) -> str:
        return f"{PRISM_COMPONENTS}/prism-{language}.min.js"

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> bytes:
        response = await session.get(url)
        response.raise_for_status()
        return await response.read()

    async def download(self) -> tuple[str, str]:
        if not self._config.enabled:
            return "", ""
        theme_url = f"{PRISM_THEMES}/prism-{self._config.theme}.min.css"
        core_url = f"{PRISM_COMPONENTS}/prism-core.min.js"

        css_path = settings.static_dir / "prism.css"
        js_path = settings.static_dir / "prism.js"

        async with aiohttp.ClientSession() as session:
            css_bytes = await self._fetch(session, theme_url)
            async with aiofiles.open(css_path, "wb") as f:
                await f.write(css_bytes)

            js_buf = await self._fetch(session, core_url)
            for language in self._config.language_list:
                js_buf += b"\n" + await self._fetch(session, self._language_url(language))
            async with aiofiles.open(js_path, "wb") as f:
                await f.write(js_buf)

        return css_bytes.decode("utf-8"), js_buf.decode("utf-8")

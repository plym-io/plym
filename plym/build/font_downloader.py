import asyncio
import hashlib
import json
import logging
import re
from urllib.parse import parse_qs, quote, urlparse

import aiofiles
import aiohttp

from plym.build.constants import BASE_URL, HTTP_TIMEOUT, METADATA_URL, TEXT, USER_AGENT
from plym.config.site import SiteConfig
from plym.settings import settings

log = logging.getLogger("plym.build")

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

# css2 responses degrade rather than fail: an unknown weight comes back as a 200
# with that face silently absent, and the request only 400s when nothing at all
# can be served. Every requested face is therefore checked against the response.
_FACE_PATTERN = re.compile(r"font-family:\s*'([^']+)';[^}]*?font-weight:\s*(\d+)", re.DOTALL)

_METADATA_PREFIX = ")]}'"


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
        self._fonts = site.fonts
        self._prefix = site.blog_prefix

    def _families(self) -> dict[str, list[int]]:
        families: dict[str, set[int]] = {}
        for _, slot in self._fonts.slots():
            families.setdefault(slot.family, set()).update(slot.weights.values())
        return {family: sorted(weights) for family, weights in families.items()}

    def _url(self, family: str, weights: list[int]) -> str:
        wght = ";".join(str(weight) for weight in weights)
        return f"{BASE_URL}?family={family}:wght@{wght}&display=swap&text={quote(TEXT)}"

    @staticmethod
    async def _available_weights(session: aiohttp.ClientSession, family: str) -> str:
        # Purely diagnostic, and the response shape is a third party's: no
        # failure here may ever escape and cost the build its webfonts.
        try:
            response = await session.get(METADATA_URL.format(family=quote(family)))
            response.raise_for_status()
            metadata = json.loads((await response.text()).removeprefix(_METADATA_PREFIX))
            for axis in metadata.get("axes", []):
                if axis.get("tag") == "wght":
                    return f"{axis['min']:g}-{axis['max']:g} (variable)"
            weights = sorted({int(v) for v in metadata.get("fonts", {}) if v.isdigit()})
        except Exception:
            return "unknown (metadata unavailable)"
        if not weights:
            return "unknown (metadata unavailable)"
        return ", ".join(str(weight) for weight in weights)

    async def _family_css(
        self, session: aiohttp.ClientSession, family: str, weights: list[int]
    ) -> str:
        try:
            response = await session.get(self._url(family, weights))
            response.raise_for_status()
            css = await response.text()
        except (TimeoutError, aiohttp.ClientError) as exc:
            log.warning(
                "webfonts: request for %s failed (%s); the family offers %s — "
                "continuing without it",
                family,
                exc,
                await self._available_weights(session, family),
            )
            return ""
        returned = {int(w) for name, w in _FACE_PATTERN.findall(css) if name == family}
        if not returned:
            log.warning(
                "webfonts: %s returned no usable faces; the family offers %s — "
                "continuing without it",
                family,
                await self._available_weights(session, family),
            )
            return ""
        missing = [weight for weight in weights if weight not in returned]
        if missing:
            log.warning(
                "webfonts: %s has no %s face; the family offers %s — keeping %s",
                family,
                ", ".join(str(weight) for weight in missing),
                await self._available_weights(session, family),
                ", ".join(str(weight) for weight in sorted(returned)),
            )
        return css

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
            parts = await asyncio.gather(
                *(
                    self._family_css(session, family, weights)
                    for family, weights in self._families().items()
                )
            )
            css = "\n".join(part for part in parts if part)

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

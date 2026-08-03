import base64
import hashlib
import hmac
import io
import json
import logging
import re
import tarfile

import aiofiles
import aiohttp

from plym.build.constants import (
    PRISM_PACKAGE_ROOT,
    PRISM_TARBALL_NPM_INTEGRITY,
    PRISM_TARBALL_URL,
    PRISM_TIMEOUT,
    PRISM_VERSION,
    USER_AGENT,
)
from plym.config.site import PrismConfig
from plym.settings import settings

log = logging.getLogger("plym.build.prism")

_ASSET_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")


class PrismIntegrityError(RuntimeError):
    pass


class PrismAssetError(RuntimeError):
    pass


def _as_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _asset_name(kind: str, value: str) -> str:
    if not _ASSET_NAME.fullmatch(value):
        raise PrismAssetError(
            f"prism {kind} {value!r} is not a valid prismjs asset name; "
            "expected lowercase letters, digits and hyphens only"
        )
    return value


class PrismJsDownloader:
    def __init__(self, config: PrismConfig) -> None:
        self._config = config

    async def download(self) -> tuple[str, str]:
        if not self._config.enabled:
            return "", ""

        theme = _asset_name("theme", self._config.theme)
        languages = [_asset_name("language", lang) for lang in self._config.language_list]

        archive = await self._fetch_archive()
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            css_bytes = self._member(tar, f"themes/prism-{theme}.min.css")
            languages = self._dependency_order(tar, languages)
            chunks = [self._member(tar, "components/prism-core.min.js")]
            chunks += [
                self._member(tar, f"components/prism-{language}.min.js") for language in languages
            ]
        js_bytes = b"\n".join(chunks)

        async with aiofiles.open(settings.static_dir / "prism.css", "wb") as f:
            await f.write(css_bytes)
        async with aiofiles.open(settings.static_dir / "prism.js", "wb") as f:
            await f.write(js_bytes)

        log.info(
            "prismjs@%s verified and unpacked: theme=%s languages=%s css=%dB js=%dB",
            PRISM_VERSION,
            theme,
            ",".join(languages) or "-",
            len(css_bytes),
            len(js_bytes),
        )
        return css_bytes.decode("utf-8"), js_bytes.decode("utf-8")

    def _dependency_order(self, tar: tarfile.TarFile, languages: list[str]) -> list[str]:
        catalog = json.loads(self._member(tar, "components.json").decode("utf-8"))["languages"]
        canonical = {
            alias: name
            for name, entry in catalog.items()
            if name != "meta"
            for alias in _as_list(entry.get("alias"))
        }

        ordered: list[str] = []
        resolved: set[str] = set()

        def include(name: str, trail: frozenset[str]) -> None:
            name = canonical.get(name, name)
            if name in resolved:
                return
            if name in trail:
                raise PrismAssetError(
                    f"prismjs@{PRISM_VERSION} components.json declares a dependency "
                    f"cycle involving {name!r}"
                )
            for dep in _as_list(catalog.get(name, {}).get("require")):
                include(dep, trail | {name})
            resolved.add(name)
            ordered.append(name)

        for language in languages:
            include(language, frozenset())
        return ordered

    async def _fetch_archive(self) -> bytes:
        async with aiohttp.ClientSession(
            timeout=PRISM_TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as session:
            response = await session.get(PRISM_TARBALL_URL)
            response.raise_for_status()
            payload = await response.read()
        self._verify(payload)
        return payload

    @staticmethod
    def _verify(payload: bytes) -> None:
        algorithm, _, expected = PRISM_TARBALL_NPM_INTEGRITY.partition("-")
        actual = base64.b64encode(hashlib.new(algorithm, payload).digest()).decode()
        if not hmac.compare_digest(actual, expected):
            raise PrismIntegrityError(
                f"{PRISM_TARBALL_URL} failed integrity check: expected "
                f"{algorithm}-{expected}, got {algorithm}-{actual} over {len(payload)}B — "
                "refusing to inline unverified JavaScript into published pages"
            )

    @staticmethod
    def _member(tar: tarfile.TarFile, path: str) -> bytes:
        name = f"{PRISM_PACKAGE_ROOT}/{path}"
        try:
            handle = tar.extractfile(name)
        except KeyError as exc:
            raise PrismAssetError(
                f"prismjs@{PRISM_VERSION} contains no {path}; check the prism theme "
                "and languages in config.yaml"
            ) from exc
        if handle is None:
            raise PrismAssetError(f"prismjs@{PRISM_VERSION} entry {path} is not a regular file")
        return handle.read()

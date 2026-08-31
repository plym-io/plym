import base64
import hashlib
import io
import os
import re
import tarfile
from pathlib import Path

import pytest
from PIL import Image

os.environ.setdefault("PLYM_JWT_SECRET", "plym-build-contract-unit-tests")

from plym.build import font_downloader, prism_downloader
from plym.build.constants import BASE_URL, PRISM_TARBALL_URL
from plym.build.pipeline import run_build
from plym.config.site import SiteConfig
from plym.settings import settings

# The serving layers (Caddy in OSS, the Worker on cloud) cache /static/ and
# /webfonts/ downstream for a year, immutable. That is only sound while every
# file the build puts there dies with its content — name = stem-<hash>.<ext>.
# Mutable build inputs belong in build_dir, which is never served or synced.
IMMUTABLE_NAME = re.compile(r"^[a-z0-9]+-[0-9a-f]{8,}\.[a-z0-9]+$")

WOFF2 = b"wOF2" + b"\x00" * 28
FONT_URL = "https://fonts.gstatic.com/l/font?kit=UcC73Fwr&skey=c491285d6722e4fa&v=v20"
FONT_CSS = "\n".join(
    f"@font-face {{ font-family: '{family}'; font-style: normal; font-weight: {weight}; "
    f"src: url({FONT_URL}) format('woff2'); }}"
    for family, weight in (("Inter", 600), ("Inter", 900), ("Merriweather", 400))
)


def _image(fmt: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(buf, format=fmt)
    return buf.getvalue()


def _tarball() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        entries = {
            "components.json": b'{"languages": {"meta": {}, "python": {}}}',
            "themes/prism-tomorrow.min.css": b"code[class*=language-]{}",
            "components/prism-core.min.js": b"var Prism={};",
            "components/prism-python.min.js": b"Prism.languages.python={};",
        }
        for name, data in entries.items():
            info = tarfile.TarInfo(f"package/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    async def text(self) -> str:
        return self._body.decode()

    async def read(self) -> bytes:
        return self._body


class _Session:
    def __init__(self, responses: dict[str, bytes]) -> None:
        self._responses = responses

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *excinfo: object) -> None:
        return None

    async def get(self, url: str) -> _Response:
        for prefix, body in self._responses.items():
            if url.startswith(prefix):
                return _Response(body)
        raise AssertionError(f"unexpected fetch during build: {url}")


@pytest.mark.asyncio
async def test_served_asset_dirs_contain_only_immutable_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    static = tmp_path / "static"
    fonts = tmp_path / "webfonts"
    build = tmp_path / "build"
    for directory in (static, fonts, build):
        directory.mkdir()
    monkeypatch.setattr(settings, "static_dir", static)
    monkeypatch.setattr(settings, "fonts_dir", fonts)
    monkeypatch.setattr(settings, "build_dir", build)

    for legacy in ("fonts.css", "prism.css", "prism.js"):
        (static / legacy).write_text("written by a release before build_dir existed")

    tarball = _tarball()
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(tarball).digest()).decode()
    monkeypatch.setattr(prism_downloader, "PRISM_TARBALL_NPM_INTEGRITY", integrity)
    monkeypatch.setattr(
        font_downloader.aiohttp,
        "ClientSession",
        lambda **kwargs: _Session(
            {
                BASE_URL: FONT_CSS.encode(),
                "https://fonts.gstatic.com/": WOFF2,
                PRISM_TARBALL_URL: tarball,
                "https://example.com/logo.png": _image("PNG"),
                "https://example.com/favicon.ico": _image("ICO"),
            }
        ),
    )

    site = SiteConfig(
        logo="https://example.com/logo.png", favicon="https://example.com/favicon.ico"
    )
    site.prism.enabled = True
    artifacts = await run_build(site)

    static_names = sorted(p.name for p in static.iterdir())
    font_names = sorted(p.name for p in fonts.iterdir())
    assert any(name.startswith("logo-") for name in static_names)
    assert any(name.startswith("favicon-") for name in static_names)
    assert font_names, "the build produced no webfonts — the contract check ran on nothing"
    for name in static_names + font_names:
        assert IMMUTABLE_NAME.match(name), (
            f"{name} is served with a year-long immutable cache lifetime but its name "
            "does not bind it to its content; write mutable files to settings.build_dir"
        )

    assert sorted(p.name for p in build.iterdir()) == ["fonts.css", "prism.css", "prism.js"]
    assert "@font-face" in artifacts.css
    assert artifacts.prism_js == "var Prism={};\nPrism.languages.python={};"

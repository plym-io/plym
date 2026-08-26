import io
import os
from pathlib import Path
from typing import cast

import aiohttp
import pytest
from PIL import Image

os.environ.setdefault("PLYM_JWT_SECRET", "plym-asset-downloader-unit-tests")

from plym.build.asset_downloader import AssetDownloader
from plym.config.site import SiteConfig
from plym.settings import settings

SVG = b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"/>'


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    async def read(self) -> bytes:
        return self._body


class _Session:
    def __init__(self, body: bytes) -> None:
        self._body = body

    async def get(self, url: str) -> _Response:
        return _Response(self._body)


def _png(color: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def static_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "static_dir", tmp_path)
    return tmp_path


def _downloader() -> AssetDownloader:
    return AssetDownloader(SiteConfig(logo="https://example.com/logo.svg"))


def _session(body: bytes) -> aiohttp.ClientSession:
    return cast(aiohttp.ClientSession, _Session(body))


@pytest.mark.asyncio
async def test_an_svg_logo_is_stored_untouched(static_dir: Path) -> None:
    asset = await _downloader()._logo(_session(SVG), "https://example.com/logo.svg")

    assert asset is not None
    assert asset.web_path.endswith(".svg")
    stored = static_dir / Path(asset.web_path).name
    assert stored.read_bytes() == SVG


@pytest.mark.asyncio
async def test_an_svg_behind_a_comment_is_still_recognised(static_dir: Path) -> None:
    body = b"<!-- " + b"x" * 2000 + b" -->\n" + SVG
    asset = await _downloader()._logo(_session(body), "https://example.com/logo.svg")

    assert asset is not None
    assert asset.web_path.endswith(".svg")


@pytest.mark.asyncio
async def test_a_raster_logo_is_still_converted_to_webp(static_dir: Path) -> None:
    asset = await _downloader()._logo(_session(_png("red")), "https://example.com/logo.png")

    assert asset is not None
    assert asset.web_path.endswith(".webp")
    with Image.open(static_dir / Path(asset.web_path).name) as image:
        assert image.format == "WEBP"


@pytest.mark.asyncio
async def test_switching_logo_format_removes_the_previous_file(static_dir: Path) -> None:
    downloader = _downloader()
    raster = await downloader._logo(_session(_png("red")), "https://example.com/logo.png")
    assert raster is not None

    vector = await downloader._logo(_session(SVG), "https://example.com/logo.svg")
    assert vector is not None

    assert sorted(p.name for p in static_dir.iterdir()) == [Path(vector.web_path).name]


@pytest.mark.asyncio
async def test_an_unreadable_logo_is_dropped(static_dir: Path) -> None:
    asset = await _downloader()._logo(_session(b"not an image"), "https://example.com/logo.png")

    assert asset is None
    assert list(static_dir.iterdir()) == []

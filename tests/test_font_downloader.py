import hashlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("PLYM_JWT_SECRET", "plym-font-downloader-unit-tests")

from plym.build import font_downloader
from plym.build.font_downloader import UnrecognizedFontError, WebFontDownloader
from plym.config.site import SiteConfig
from plym.settings import settings

SKEY_URL = "https://fonts.gstatic.com/l/font?kit=UcC73Fwr&skey=c491285d6722e4fa&v=v20"
WOFF2 = b"wOF2" + b"\x00" * 28


def _css(url: str) -> str:
    return f"@font-face {{ font-family: 'Inter'; src: url({url}) format('woff2'); }}"


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
    def __init__(self, css: str, fonts: dict[str, bytes]) -> None:
        self._css = css
        self._fonts = fonts

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *excinfo: object) -> None:
        return None

    async def get(self, url: str) -> _Response:
        if url in self._fonts:
            return _Response(self._fonts[url])
        return _Response(self._css.encode())


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fonts = tmp_path / "webfonts"
    static = tmp_path / "static"
    build = tmp_path / "build"
    fonts.mkdir()
    static.mkdir()
    build.mkdir()
    monkeypatch.setattr(settings, "fonts_dir", fonts)
    monkeypatch.setattr(settings, "static_dir", static)
    monkeypatch.setattr(settings, "build_dir", build)
    return fonts


def _serve(monkeypatch: pytest.MonkeyPatch, css: str, fonts: dict[str, bytes]) -> None:
    monkeypatch.setattr(
        font_downloader.aiohttp, "ClientSession", lambda **kwargs: _Session(css, fonts)
    )


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:8]


@pytest.mark.asyncio
async def test_filenames_carry_the_content_hash_and_extension(
    storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(monkeypatch, _css(SKEY_URL), {SKEY_URL: WOFF2})

    site = SiteConfig(blog_prefix="blog", blog_home="https://plym.local/blog")
    css = await WebFontDownloader(site).download()

    filename = f"c491285d6722e4fa-{_digest(WOFF2)}.woff2"
    assert (storage / filename).read_bytes() == WOFF2
    assert f"/blog/webfonts/{filename}" in css
    assert SKEY_URL not in css


def test_the_same_skey_names_change_with_the_bytes() -> None:
    recut = b"wOF2" + b"\x01" * 28

    assert WebFontDownloader._filename(SKEY_URL, WOFF2) != WebFontDownloader._filename(
        SKEY_URL, recut
    )


def test_a_url_without_skey_falls_back_to_the_path_stem() -> None:
    url = "https://fonts.gstatic.com/s/inter/v13/UcC73Fwr.woff2"

    assert WebFontDownloader._filename(url, WOFF2) == f"UcC73Fwr-{_digest(WOFF2)}.woff2"


def test_an_unrecognized_payload_is_a_typed_error() -> None:
    with pytest.raises(UnrecognizedFontError):
        WebFontDownloader._filename(SKEY_URL, b"<html>not a font</html>")


@pytest.mark.asyncio
async def test_stale_fonts_are_pruned(storage: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (storage / "c491285d6722e4fa").write_bytes(b"legacy bare-skey artifact")
    (storage / "c491285d6722e4fa-deadbeef.woff2").write_bytes(b"previous subset")
    _serve(monkeypatch, _css(SKEY_URL), {SKEY_URL: WOFF2})

    await WebFontDownloader(SiteConfig()).download()

    assert sorted(p.name for p in storage.iterdir()) == [f"c491285d6722e4fa-{_digest(WOFF2)}.woff2"]


@pytest.mark.asyncio
async def test_two_payloads_sharing_a_skey_both_survive(
    storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other_url = "https://fonts.gstatic.com/l/font?kit=Different&skey=c491285d6722e4fa&v=v20"
    other = b"wOF2" + b"\x02" * 28
    css = _css(SKEY_URL) + "\n" + _css(other_url)
    _serve(monkeypatch, css, {SKEY_URL: WOFF2, other_url: other})

    await WebFontDownloader(SiteConfig()).download()

    assert sorted(p.name for p in storage.iterdir()) == sorted(
        [
            f"c491285d6722e4fa-{_digest(WOFF2)}.woff2",
            f"c491285d6722e4fa-{_digest(other)}.woff2",
        ]
    )

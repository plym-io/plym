import hashlib
import logging
import os
from pathlib import Path

import aiohttp
import pytest

os.environ.setdefault("PLYM_JWT_SECRET", "plym-font-downloader-unit-tests")

from plym.build import font_downloader
from plym.build.font_downloader import UnrecognizedFontError, WebFontDownloader
from plym.config.site import SiteConfig
from plym.settings import settings

SKEY_URL = "https://fonts.gstatic.com/l/font?kit=UcC73Fwr&skey=c491285d6722e4fa&v=v20"
BODY_URL = "https://fonts.gstatic.com/l/font?kit=u-440qyr&skey=14b9066f4e1e4a2b&v=v31"
WOFF2 = b"wOF2" + b"\x00" * 28
BODY_WOFF2 = b"wOF2" + b"\x03" * 28

METADATA_VARIABLE = (
    b')]}\'\n{"axes": [{"tag": "wght", "min": 300.0, "max": 900.0}], "fonts": {"400": {}}}'
)
METADATA_STATIC = b")]}'\n" + b'{"axes": [], "fonts": {"400": {}, "700i": {}}}'


def _face(family: str, weight: int, url: str) -> str:
    return (
        f"@font-face {{ font-family: '{family}'; font-style: normal; "
        f"font-weight: {weight}; src: url({url}) format('woff2'); }}"
    )


class _Response:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self._status = status

    def raise_for_status(self) -> None:
        if self._status >= 400:
            raise aiohttp.ClientError(f"HTTP {self._status}")

    async def text(self) -> str:
        return self._body.decode()

    async def read(self) -> bytes:
        return self._body


class _Session:
    """Routes by substring match; unrouted URLs answer 400."""

    def __init__(self, routes: dict[str, bytes]) -> None:
        self._routes = routes
        self.requests: list[str] = []

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *excinfo: object) -> None:
        return None

    async def get(self, url: str) -> _Response:
        self.requests.append(url)
        for key, body in self._routes.items():
            if key in url:
                return _Response(body)
        return _Response(b"", status=400)


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


def _serve(monkeypatch: pytest.MonkeyPatch, routes: dict[str, bytes]) -> _Session:
    session = _Session(routes)
    monkeypatch.setattr(font_downloader.aiohttp, "ClientSession", lambda **kwargs: session)
    return session


def _default_routes() -> dict[str, bytes]:
    return {
        "family=Inter:wght@600": _face("Inter", 600, SKEY_URL).encode(),
        "family=Merriweather:wght@400": _face("Merriweather", 400, BODY_URL).encode(),
        SKEY_URL: WOFF2,
        BODY_URL: BODY_WOFF2,
    }


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:8]


@pytest.mark.asyncio
async def test_filenames_carry_the_content_hash_and_extension(
    storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(monkeypatch, _default_routes())

    site = SiteConfig(blog_prefix="blog", blog_home="https://plym.local/blog")
    css = await WebFontDownloader(site).download()

    filename = f"c491285d6722e4fa-{_digest(WOFF2)}.woff2"
    assert (storage / filename).read_bytes() == WOFF2
    assert f"/blog/webfonts/{filename}" in css
    assert SKEY_URL not in css


@pytest.mark.asyncio
async def test_each_family_is_requested_once_with_its_weight_union(
    storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    css = "\n".join(_face("Inter", w, SKEY_URL) for w in (400, 600))
    session = _serve(monkeypatch, {"family=Inter:wght@400;600": css.encode(), SKEY_URL: WOFF2})

    site = SiteConfig(fonts={"heading": "Inter", "body": "Inter"})
    await WebFontDownloader(site).download()

    css2 = [url for url in session.requests if "css2" in url]
    assert len(css2) == 1
    assert "family=Inter:wght@400;600" in css2[0]


@pytest.mark.asyncio
async def test_a_family_returning_no_faces_is_dropped_and_the_rest_kept(
    storage: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    routes = _default_routes()
    routes["family=Merriweather:wght@400"] = b"/* nothing */"
    routes["metadata/fonts/Merriweather"] = METADATA_VARIABLE
    _serve(monkeypatch, routes)

    with caplog.at_level(logging.WARNING, logger="plym.build"):
        css = await WebFontDownloader(SiteConfig()).download()

    assert "'Inter'" in css
    assert "Merriweather" not in css
    assert sorted(p.name for p in storage.iterdir()) == [f"c491285d6722e4fa-{_digest(WOFF2)}.woff2"]
    warning = next(r.message for r in caplog.records if "Merriweather" in r.message)
    assert "300-900 (variable)" in warning
    assert "continuing without it" in warning


@pytest.mark.asyncio
async def test_a_missing_weight_keeps_the_faces_that_came_back(
    storage: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    routes = _default_routes()
    routes["family=Lobster:wght@400;700"] = _face("Lobster", 400, BODY_URL).encode()
    routes["metadata/fonts/Lobster"] = METADATA_STATIC
    _serve(monkeypatch, routes)

    site = SiteConfig(
        fonts={"body": {"family": "Lobster", "weights": {"regular": 400, "bold": 700}}}
    )
    with caplog.at_level(logging.WARNING, logger="plym.build"):
        css = await WebFontDownloader(site).download()

    assert "'Lobster'" in css
    warning = next(r.message for r in caplog.records if "Lobster" in r.message)
    assert "700" in warning
    assert "offers 400" in warning
    assert "keeping 400" in warning


@pytest.mark.asyncio
async def test_a_400_from_css2_never_raises(
    storage: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _serve(monkeypatch, {})

    with caplog.at_level(logging.WARNING, logger="plym.build"):
        css = await WebFontDownloader(SiteConfig()).download()

    assert css == ""
    assert (settings.build_dir / "fonts.css").read_text() == ""
    assert [r for r in caplog.records if "Inter" in r.message]
    assert [r for r in caplog.records if "Merriweather" in r.message]


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
async def test_stale_fonts_are_pruned_once_across_families(
    storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (storage / "c491285d6722e4fa").write_bytes(b"legacy bare-skey artifact")
    (storage / "c491285d6722e4fa-deadbeef.woff2").write_bytes(b"previous subset")
    _serve(monkeypatch, _default_routes())

    await WebFontDownloader(SiteConfig()).download()

    assert sorted(p.name for p in storage.iterdir()) == sorted(
        [
            f"c491285d6722e4fa-{_digest(WOFF2)}.woff2",
            f"14b9066f4e1e4a2b-{_digest(BODY_WOFF2)}.woff2",
        ]
    )


@pytest.mark.asyncio
async def test_two_payloads_sharing_a_skey_both_survive(
    storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other_url = "https://fonts.gstatic.com/l/font?kit=Different&skey=c491285d6722e4fa&v=v20"
    other = b"wOF2" + b"\x02" * 28
    routes = {
        "family=Inter:wght@400;600": "\n".join(
            [_face("Inter", 600, SKEY_URL), _face("Inter", 400, other_url)]
        ).encode(),
        SKEY_URL: WOFF2,
        other_url: other,
    }
    _serve(monkeypatch, routes)

    await WebFontDownloader(SiteConfig(fonts={"heading": "Inter", "body": "Inter"})).download()

    assert sorted(p.name for p in storage.iterdir()) == sorted(
        [
            f"c491285d6722e4fa-{_digest(WOFF2)}.woff2",
            f"c491285d6722e4fa-{_digest(other)}.woff2",
        ]
    )


@pytest.mark.asyncio
async def test_a_plus_separated_family_name_is_normalized_not_dropped(
    storage: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    routes = _default_routes()
    routes["family=Hanken Grotesk:wght@600"] = _face("Hanken Grotesk", 600, SKEY_URL).encode()
    session = _serve(monkeypatch, routes)

    site = SiteConfig(fonts={"heading": "Hanken+Grotesk"})
    with caplog.at_level(logging.WARNING, logger="plym.build"):
        css = await WebFontDownloader(site).download()

    assert "'Hanken Grotesk'" in css
    assert not caplog.records
    assert any("family=Hanken Grotesk:wght@600" in url for url in session.requests)


@pytest.mark.asyncio
async def test_malformed_axis_metadata_cannot_kill_the_build(
    storage: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    routes = _default_routes()
    routes["family=Merriweather:wght@400;700"] = _face("Merriweather", 400, BODY_URL).encode()
    routes["metadata/fonts/Merriweather"] = b")]}'\n" + b'{"axes": [{"tag": "wght"}], "fonts": {}}'
    _serve(monkeypatch, routes)

    site = SiteConfig(
        fonts={"body": {"family": "Merriweather", "weights": {"regular": 400, "bold": 700}}}
    )
    with caplog.at_level(logging.WARNING, logger="plym.build"):
        css = await WebFontDownloader(site).download()

    assert "'Inter'" in css
    assert "'Merriweather'" in css
    warning = next(r.message for r in caplog.records if "Merriweather" in r.message)
    assert "unknown (metadata unavailable)" in warning


@pytest.mark.asyncio
async def test_a_slot_requests_exactly_the_weights_it_declares(
    storage: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    routes = _default_routes()
    routes["family=Lobster:wght@400&"] = _face("Lobster", 400, BODY_URL).encode()
    session = _serve(monkeypatch, routes)

    site = SiteConfig(fonts={"body": {"family": "Lobster", "weights": {"regular": 400}}})
    with caplog.at_level(logging.WARNING, logger="plym.build"):
        css = await WebFontDownloader(site).download()

    assert "'Lobster'" in css
    assert not caplog.records
    assert any("family=Lobster:wght@400&" in url for url in session.requests)

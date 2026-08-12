from pathlib import Path
from typing import Any

import pytest

from tests.conftest import TEST_MODE

# Importing plym.main builds the app, which loads the host's config.yaml. In live mode the
# suite is pointed at a server that already did that, so importing it here only couples these
# tests to whatever config happens to sit next to the checkout — hence the deferred imports.
pytestmark = pytest.mark.skipif(
    TEST_MODE != "inprocess", reason="drives the AdminSPA class in process, not a served instance"
)


@pytest.fixture
def admin_build(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<head></head><body>admin</body>", encoding="utf-8")
    (tmp_path / "assets" / "index-BW2KWlRl.js").write_text("export default 1", encoding="utf-8")
    (tmp_path / "logo.svg").write_text("<svg/>", encoding="utf-8")
    return tmp_path


def _scope(path: str) -> dict[str, Any]:
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
    }


@pytest.mark.asyncio
async def test_the_shell_is_never_stored(admin_build: Path) -> None:
    from plym.main import SHELL_CACHE_CONTROL, AdminSPA

    spa = AdminSPA(str(admin_build), "/plym-admin")

    for path in ("", "index.html", "posts/42"):
        response = await spa.get_response(path, _scope(f"/{path}"))
        assert response.headers["cache-control"] == SHELL_CACHE_CONTROL


@pytest.mark.asyncio
async def test_content_hashed_bundles_are_immutable(admin_build: Path) -> None:
    from plym.main import HASHED_ASSET_CACHE_CONTROL, AdminSPA

    spa = AdminSPA(str(admin_build), "/plym-admin")

    response = await spa.get_response(
        "assets/index-BW2KWlRl.js", _scope("/assets/index-BW2KWlRl.js")
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == HASHED_ASSET_CACHE_CONTROL


@pytest.mark.asyncio
async def test_unhashed_assets_revalidate(admin_build: Path) -> None:
    from plym.main import UNHASHED_ASSET_CACHE_CONTROL, AdminSPA

    spa = AdminSPA(str(admin_build), "/plym-admin")

    response = await spa.get_response("logo.svg", _scope("/logo.svg"))
    assert response.status_code == 200
    assert response.headers["cache-control"] == UNHASHED_ASSET_CACHE_CONTROL


def test_only_hashed_files_under_assets_are_treated_as_immutable() -> None:
    from plym.main import (
        HASHED_ASSET_CACHE_CONTROL,
        UNHASHED_ASSET_CACHE_CONTROL,
        admin_cache_control,
    )

    immutable = [
        "assets/index-BW2KWlRl.js",
        "assets/asterisk-B-8jnY81.js",
        "assets/d-pRatUO7H.js",
        "/assets/style-CHzPgrmr.css",
    ]
    for path in immutable:
        assert admin_cache_control(path) == HASHED_ASSET_CACHE_CONTROL, path

    # A hash-shaped name outside assets/, or an unhashed name inside it, must fall back —
    # a wrong "immutable" is unrecallable, a wrong "no-cache" only costs a round trip.
    revalidated = [
        "index.html",
        "logo.svg",
        "favicon.webp",
        "assets/vendor.js",
        "some-filename.js",
        "assets/index-short.js",
    ]
    for path in revalidated:
        assert admin_cache_control(path) == UNHASHED_ASSET_CACHE_CONTROL, path

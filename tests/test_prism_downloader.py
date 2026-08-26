import io
import json
import os
import tarfile

import pytest

os.environ.setdefault("PLYM_JWT_SECRET", "plym-prism-unit-tests")

from plym.build.prism_downloader import PrismAssetError, PrismJsDownloader
from plym.config.site import PrismConfig

CATALOG = {
    "languages": {
        "meta": {"path": "components/prism-{id}"},
        "markup": {"alias": ["html", "xml", "svg"]},
        "clike": {},
        "css": {},
        "python": {"alias": "py"},
        "yaml": {"alias": "yml"},
        "markup-templating": {"require": "markup"},
        "django": {"require": "markup-templating", "alias": "jinja2"},
        "cpp": {"require": ["c"]},
        "c": {"require": "clike"},
        "looper-a": {"require": "looper-b"},
        "looper-b": {"require": "looper-a"},
    }
}


def _tar_with_catalog() -> tarfile.TarFile:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        payload = json.dumps(CATALOG).encode("utf-8")
        info = tarfile.TarInfo("package/components.json")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    buf.seek(0)
    return tarfile.open(fileobj=buf, mode="r:gz")


def _order(languages: list[str]) -> list[str]:
    downloader = PrismJsDownloader(PrismConfig(enabled=True))
    with _tar_with_catalog() as tar:
        return downloader._dependency_order(tar, languages)


def test_requirements_load_before_dependents() -> None:
    order = _order(["python", "markup", "css", "clike", "django", "markup-templating", "yaml"])
    assert order == ["python", "markup", "css", "clike", "markup-templating", "django", "yaml"]


def test_missing_requirements_are_pulled_in() -> None:
    assert _order(["django"]) == ["markup", "markup-templating", "django"]


def test_requirement_lists_resolve_transitively() -> None:
    assert _order(["cpp"]) == ["clike", "c", "cpp"]


def test_config_order_is_preserved_for_independents() -> None:
    assert _order(["yaml", "css", "python"]) == ["yaml", "css", "python"]


def test_aliases_resolve_to_canonical_components() -> None:
    assert _order(["html", "yml", "jinja2"]) == [
        "markup",
        "yaml",
        "markup-templating",
        "django",
    ]


def test_duplicates_collapse() -> None:
    assert _order(["python", "py", "python"]) == ["python"]


def test_unknown_language_passes_through() -> None:
    assert _order(["rust"]) == ["rust"]


def test_dependency_cycle_is_reported() -> None:
    with pytest.raises(PrismAssetError, match="cycle"):
        _order(["looper-a"])

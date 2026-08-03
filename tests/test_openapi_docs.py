import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# The app is built at import time from settings, so each debug state gets its
# own child process; requests stay off the blog router to keep the probe
# database-free.
_DOCS_PROBE = textwrap.dedent(
    """
    import asyncio, sys

    import httpx

    from plym.config.site import load_site_config
    from plym.main import app
    from plym.settings import settings

    app.state.site = load_site_config()
    app.state.css = ""
    app.state.prism_js = ""

    paths = {getattr(route, "path", None) for route in app.routes}
    mounted = "/plym-docs" in paths and "/plym-docs/openapi.json" in paths

    if mounted is not settings.debug:
        sys.exit(1)


    async def main() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://probe") as c:
            anonymous = await c.get("/api/openapi.json")
            if not settings.debug:
                print(anonymous.status_code)
                sys.exit(0 if anonymous.status_code == 401 else 1)
            ui = await c.get("/plym-docs")
            schema = await c.get("/plym-docs/openapi.json")
        print(anonymous.status_code, ui.status_code, schema.status_code)
        ok = (
            anonymous.status_code == 401
            and ui.status_code == 200
            and "swagger" in ui.text.lower()
            and schema.status_code == 200
            and schema.json()["info"]["title"] == "Plym"
        )
        sys.exit(0 if ok else 1)


    asyncio.run(main())
    """
)


@pytest.mark.parametrize("debug", ["true", "false"])
def test_docs_are_debug_only_and_api_spec_stays_protected(tmp_path: Path, debug: str) -> None:
    storage = tmp_path / "storage"
    for name in ("_uploads", ".generated", "backups", "webfonts", "static"):
        (storage / name).mkdir(parents=True)
    config = tmp_path / "config.yaml"
    config.write_text('blog_prefix: "/"\nwebsite: plym.local\n', encoding="utf-8")

    probe = subprocess.run(
        [sys.executable, "-c", _DOCS_PROBE],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PLYM_DEBUG": debug,
            "PLYM_CONFIG_PATH": str(config),
            "PLYM_STORAGE_DIR": str(storage),
            "PLYM_UPLOADS_DIR": str(storage / "_uploads"),
            "PLYM_GENERATED_DIR": str(storage / ".generated"),
            "PLYM_BACKUPS_DIR": str(storage / "backups"),
            "PLYM_FONTS_DIR": str(storage / "webfonts"),
            "PLYM_STATIC_DIR": str(storage / "static"),
            "PLYM_JWT_SECRET": "probe-secret-0123456789abcdef",
            "PLYM_SUPERUSER_EMAIL": "root@plym.local",
            "PLYM_SUPERUSER_PASSWORD": "probe-password",
            "PLYM_TRACE_EXPORTER": "none",
        },
    )
    assert probe.returncode == 0, probe.stdout + probe.stderr

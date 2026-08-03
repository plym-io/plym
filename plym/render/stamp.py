import hashlib
import re
from functools import lru_cache
from pathlib import Path

from plym.config.site import SiteConfig
from plym.settings import settings

CONTEXT_VERSION = b"1"

_CHROME_DIR = Path(__file__).parent / "chrome"
_STAMP_RE = re.compile(r'<meta name="plym-render" content="([0-9a-f]+)">')


@lru_cache(maxsize=8)
def _templates_digest(template: str) -> bytes:
    digest = hashlib.sha256()
    user_dir = settings.templates_dir / template
    for path in sorted(_CHROME_DIR.glob("*.html")) + sorted(user_dir.glob("*.html")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.digest()


def compute_render_stamp(site: SiteConfig, css: str, prism_js: str) -> str:
    digest = hashlib.sha256(CONTEXT_VERSION)
    digest.update(_templates_digest(site.template))
    digest.update(css.encode())
    digest.update(prism_js.encode())
    digest.update(site.model_dump_json().encode())
    return digest.hexdigest()[:16]


def read_render_stamp(html: str) -> str | None:
    match = _STAMP_RE.search(html)
    return match.group(1) if match else None

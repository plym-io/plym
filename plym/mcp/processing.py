import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import httpx
from markdownify import markdownify

from plym.mcp.settings import mcp_settings


def _filename_for(url: str, content_type: str | None) -> str:
    name = Path(urlparse(url).path).name
    if Path(name).suffix:
        return name
    extension = mimetypes.guess_extension((content_type or "").split(";")[0].strip()) or ""
    return f"{name or 'upload'}{extension}"


async def fetch_bytes(url: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(
        timeout=mcp_settings.request_timeout, follow_redirects=True
    ) as http:
        response = await http.get(url)
        response.raise_for_status()
        return response.content, _filename_for(url, response.headers.get("content-type"))


def html_to_markdown(html: str) -> str:
    rendered: str = markdownify(html)
    return rendered.strip()


async def fetch_html(url: str) -> str:
    async with httpx.AsyncClient(
        timeout=mcp_settings.request_timeout, follow_redirects=True
    ) as http:
        response = await http.get(url)
        response.raise_for_status()
        return response.text

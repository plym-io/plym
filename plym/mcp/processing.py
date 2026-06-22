from pathlib import Path

import aiofiles
import httpx
from fastmcp.exceptions import ToolError
from markdownify import markdownify

from plym.mcp.settings import mcp_settings


async def read_file_bytes(path: str) -> tuple[bytes, str]:
    target = Path(path).expanduser()
    if not target.is_file():
        raise ToolError(f"No readable file at {path!r}.")
    async with aiofiles.open(target, "rb") as handle:
        return await handle.read(), target.name


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

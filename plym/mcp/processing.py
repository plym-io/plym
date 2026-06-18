import httpx
from markdownify import markdownify

from plym.mcp.settings import mcp_settings


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

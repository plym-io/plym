from fastmcp.exceptions import ToolError

from plym.mcp.processing import FetchError
from plym.mcp.runtime import client, credentials, mcp


@mcp.tool
async def md_from_html(html: str) -> str:
    """Convert HTML to raw markdown"""
    return await client.markdown_from_html(credentials(), html)


@mcp.tool
async def get_from_url(url: str) -> str:
    """Get raw HTML from a given URL"""
    creds = credentials()
    try:
        return await client.html_from_url(creds, url)
    except FetchError as exc:
        raise ToolError(str(exc)) from exc

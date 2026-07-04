from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from pydantic import Base64Bytes, ValidationError

from plym.mcp.client import PlymClient
from plym.mcp.processing import fetch_bytes
from plym.models.media import MediaItem
from plym.models.post import Post, PostCreate, PostListItem
from plym.models.token import LoginRequest
from plym.models.user import User

mcp: FastMCP = FastMCP("plym")
_client = PlymClient()

_EMAIL_HEADER = "x-user-identity"
_TOKEN_HEADER = "x-mcp-token"


def _credentials() -> LoginRequest:
    headers = get_http_headers(include={_EMAIL_HEADER, _TOKEN_HEADER})
    email = headers.get(_EMAIL_HEADER)
    password = headers.get(_TOKEN_HEADER)
    if not email or not password:
        raise ToolError("Missing credentials: set the X-User-Identity and X-Mcp-Token headers.")
    try:
        return LoginRequest(email=email, password=password)
    except ValidationError as exc:
        raise ToolError("X-User-Identity is not a valid email address.") from exc


@mcp.tool
async def md_from_html(html: str) -> str:
    """Convert HTML to raw markdown"""
    return await _client.markdown_from_html(_credentials(), html)


@mcp.tool
async def get_from_url(url: str) -> str:
    """Get raw HTML from a given URL"""
    return await _client.html_from_url(_credentials(), url)


@mcp.tool
async def create_post(post: PostCreate) -> Post:
    """Create a post in your plym instance"""
    return await _client.create_post(_credentials(), post)


@mcp.tool
async def upload_media(
    url: str | None = None,
    data: Base64Bytes | None = None,
    filename: str | None = None,
) -> MediaItem:
    """Upload an image to plym; pass the returned `url` as a post's `cover`.

    Provide either `url` (a publicly reachable image) or `data`
    (base64-encoded file bytes, for images on the user's machine),
    optionally naming the upload with `filename`.
    """
    if url is not None and data is not None:
        raise ToolError("Pass either `url` or `data`, not both.")
    if url is not None:
        payload, name = await fetch_bytes(url)
    elif data is not None:
        payload, name = bytes(data), filename or "upload"
    else:
        raise ToolError("Pass `url` for a remote image, or `data` with base64-encoded file bytes.")
    return await _client.upload_media(_credentials(), payload, name)


@mcp.tool
async def list_posts() -> list[PostListItem]:
    """List all posts in your plym instance"""
    return await _client.list_posts(_credentials())


@mcp.tool
async def list_users() -> list[User]:
    """List all users in your plym instance"""
    return await _client.list_users(_credentials())

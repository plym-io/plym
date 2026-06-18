from fastmcp import FastMCP

from plym.mcp.client import PlymClient
from plym.mcp.processing import fetch_html, html_to_markdown
from plym.models.post import Post, PostCreate, PostListItem
from plym.models.token import LoginRequest
from plym.models.user import User

mcp: FastMCP = FastMCP("plym")
_client = PlymClient()


@mcp.tool
async def md_from_html(html: str, email: str, password: str) -> str:
    """Convert HTML to raw markdown"""
    await _client.login(LoginRequest(email=email, password=password))
    return html_to_markdown(html)


@mcp.tool
async def get_from_url(url: str, email: str, password: str) -> str:
    """Get raw HTML from a given URL"""
    await _client.login(LoginRequest(email=email, password=password))
    return await fetch_html(url)


@mcp.tool
async def create_post(post: PostCreate, email: str, password: str) -> Post:
    """Create a post in your plym instance"""
    return await _client.create_post(LoginRequest(email=email, password=password), post)


@mcp.tool
async def list_posts(email: str, password: str) -> list[PostListItem]:
    """List all posts in your plym instance"""
    return await _client.list_posts(LoginRequest(email=email, password=password))


@mcp.tool
async def list_users(email: str, password: str) -> list[User]:
    """List all users in your plym instance"""
    return await _client.list_users(LoginRequest(email=email, password=password))

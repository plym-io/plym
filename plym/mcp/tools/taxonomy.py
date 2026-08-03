from plym.mcp.runtime import client, credentials, mcp
from plym.models.category import Category, CategoryCreate
from plym.models.faq import Faq, FaqItem
from plym.models.tag import Tag


@mcp.tool
async def create_category(category: CategoryCreate) -> Category:
    """Create a category; pass the returned `id` as a post's `category_id`"""
    return await client.create_category(credentials(), category)


@mcp.tool
async def list_categories() -> list[Category]:
    """List all categories in your plym instance"""
    return await client.list_categories(credentials())


@mcp.tool
async def create_faq(faq: FaqItem) -> Faq:
    """Create a FAQ entry; reference the returned `id` in a post's `faqs`"""
    return await client.create_faq(credentials(), faq)


@mcp.tool
async def list_faqs() -> list[Faq]:
    """List all FAQ entries in your plym instance"""
    return await client.list_faqs(credentials())


@mcp.tool
async def list_tags() -> list[Tag]:
    """List all tags in your plym instance"""
    return await client.list_tags(credentials())

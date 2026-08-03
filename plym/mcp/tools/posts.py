from plym.mcp.runtime import client, credentials, mcp
from plym.models.post import Post, PostCreate, PostEdit, PostListItem


@mcp.tool
async def create_post(post: PostCreate) -> Post:
    """Create a post in your plym instance.

    Attach a category with `category_id` (see `list_categories`), FAQs with
    `faqs` (FAQ ids, see `list_faqs`) and tags with `tags` (plain names,
    created on the fly). The post starts as a draft; call `publish_post` to
    take it live.
    """
    return await client.create_post(credentials(), post)


@mcp.tool
async def get_post(post_id: int) -> Post:
    """Get a single post with its content, category, tags and FAQs"""
    return await client.get_post(credentials(), post_id)


@mcp.tool
async def update_post(post_id: int, edit: PostEdit) -> Post:
    """Update a post's fields, or attach a category, FAQs or tags to it.

    Only the fields set in `edit` are changed; omitted fields keep their
    current value. Publishing is separate: use `publish_post`.
    """
    return await client.update_post(credentials(), post_id, edit)


@mcp.tool
async def publish_post(post_id: int) -> Post:
    """Publish a drafted post, rendering its static HTML and markdown"""
    return await client.publish_post(credentials(), post_id)


@mcp.tool
async def list_posts() -> list[PostListItem]:
    """List all posts in your plym instance, drafts included"""
    return await client.list_posts(credentials())

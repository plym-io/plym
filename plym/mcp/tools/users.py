from plym.mcp.runtime import client, credentials, mcp
from plym.models.user import User


@mcp.tool
async def list_users() -> list[User]:
    """List all users in your plym instance"""
    return await client.list_users(credentials())

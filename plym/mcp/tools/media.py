from fastmcp.exceptions import ToolError
from pydantic import Base64Bytes

from plym.mcp.processing import FetchError, fetch_bytes
from plym.mcp.runtime import client, credentials, mcp
from plym.models.media import MediaItem


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
        try:
            payload, name = await fetch_bytes(url)
        except FetchError as exc:
            raise ToolError(str(exc)) from exc
    elif data is not None:
        payload, name = bytes(data), filename or "upload"
    else:
        raise ToolError("Pass `url` for a remote image, or `data` with base64-encoded file bytes.")
    return await client.upload_media(credentials(), payload, name)

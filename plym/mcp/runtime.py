from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from pydantic import ValidationError

from plym.mcp.client import PlymClient
from plym.models.token import LoginRequest

mcp: FastMCP = FastMCP("plym")
client = PlymClient()

_EMAIL_HEADER = "x-user-identity"
_TOKEN_HEADER = "x-mcp-token"


def credentials() -> LoginRequest:
    headers = get_http_headers(include={_EMAIL_HEADER, _TOKEN_HEADER})
    email = headers.get(_EMAIL_HEADER)
    password = headers.get(_TOKEN_HEADER)
    if not email or not password:
        raise ToolError("Missing credentials: set the X-User-Identity and X-Mcp-Token headers.")
    try:
        return LoginRequest(email=email, password=password)
    except ValidationError as exc:
        raise ToolError("X-User-Identity is not a valid email address.") from exc

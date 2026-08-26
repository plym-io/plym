from collections.abc import Iterable
from urllib.parse import urlsplit, urlunsplit

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def _host(scope: Scope) -> str:
    headers: Iterable[tuple[bytes, bytes]] = scope.get("headers", ())
    for key, value in headers:
        if key == b"host":
            return value.decode("latin-1")
    return ""


def _only_trailing_slash(request_path: str, location_path: str) -> bool:
    return request_path != location_path and request_path.rstrip("/") == location_path.rstrip("/")


class CanonicalRedirectMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] in _REDIRECT_STATUSES:
                _canonicalize(scope, message)
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _canonicalize(scope: Scope, message: Message) -> None:
    headers = MutableHeaders(raw=message["headers"])
    location = headers.get("location")
    if not location:
        return

    parts = urlsplit(location)
    if parts.netloc and parts.netloc == _host(scope):
        location = urlunsplit(("", "", parts.path, parts.query, parts.fragment)) or "/"
        headers["location"] = location
        parts = urlsplit(location)

    if message["status"] == 307 and _only_trailing_slash(scope["path"], parts.path):
        message["status"] = 308

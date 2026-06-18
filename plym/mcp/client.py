from collections.abc import Awaitable, Callable
from typing import Any, Concatenate

import httpx
from fastmcp.exceptions import ToolError

from plym.mcp.processing import fetch_html, html_to_markdown
from plym.mcp.settings import mcp_settings
from plym.models.post import Post, PostCreate, PostListItem
from plym.models.token import LoginRequest
from plym.models.user import User

type Tokenized[**P, R] = Callable[Concatenate["PlymClient", str, P], Awaitable[R]]
type Authenticated[**P, R] = Callable[Concatenate["PlymClient", LoginRequest, P], Awaitable[R]]

_PAGE_SIZE = 200


def authenticated[**P, R](method: Tokenized[P, R]) -> Authenticated[P, R]:
    async def wrapper(
        self: "PlymClient", creds: LoginRequest, /, *args: P.args, **kwargs: P.kwargs
    ) -> R:
        token = await self.login(creds)
        return await method(self, token, *args, **kwargs)

    return wrapper


class PlymClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        self._base_url = (base_url or mcp_settings.base_url).rstrip("/")
        self._timeout = timeout or mcp_settings.request_timeout

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout, follow_redirects=True
        )

    @staticmethod
    def _bearer(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def login(self, creds: LoginRequest) -> str:
        async with self._http() as http:
            response = await http.post("/api/auth/login", json=creds.model_dump(mode="json"))
            if response.status_code in (401, 403):
                raise ToolError("Authentication failed: check your email and password.")
            response.raise_for_status()
            token: str = response.json()["access_token"]
            return token

    @authenticated
    async def markdown_from_html(self, token: str, html: str) -> str:
        return html_to_markdown(html)

    @authenticated
    async def html_from_url(self, token: str, url: str) -> str:
        return await fetch_html(url)

    async def _paginate(
        self, token: str, path: str, params: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 1
        async with self._http() as http:
            while True:
                query = {"page": str(page), "page_size": str(_PAGE_SIZE), **(params or {})}
                response = await http.get(path, params=query, headers=self._bearer(token))
                if response.status_code == 403:
                    raise ToolError("This account is not allowed to list this resource.")
                response.raise_for_status()
                body = response.json()
                rows.extend(body["items"])
                if not body["items"] or len(rows) >= body["total"]:
                    break
                page += 1
        return rows

    @authenticated
    async def list_posts(self, token: str) -> list[PostListItem]:
        rows = await self._paginate(token, "/api/posts", {"include_drafts": "true"})
        return [PostListItem.model_validate(row) for row in rows]

    @authenticated
    async def list_users(self, token: str) -> list[User]:
        rows = await self._paginate(token, "/api/users")
        return [User.model_validate(row) for row in rows]

    @authenticated
    async def create_post(self, token: str, post: PostCreate) -> Post:
        async with self._http() as http:
            response = await http.post(
                "/api/posts", json=post.model_dump(mode="json"), headers=self._bearer(token)
            )
            if response.status_code == 403:
                raise ToolError("This account cannot create posts (editor role required).")
            response.raise_for_status()
            return Post.model_validate(response.json())

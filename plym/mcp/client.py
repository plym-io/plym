from collections.abc import Awaitable, Callable
from typing import Any, Concatenate

import httpx
from fastmcp.exceptions import ToolError

from plym.mcp.processing import fetch_html, html_to_markdown
from plym.mcp.settings import mcp_settings
from plym.models.category import Category, CategoryCreate
from plym.models.common import PostStatus
from plym.models.faq import Faq, FaqItem
from plym.models.media import MediaItem
from plym.models.post import Post, PostCreate, PostEdit, PostListItem
from plym.models.tag import Tag
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


def _api_message(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict) and isinstance(message := detail.get("message"), str):
        return message
    return None


class PlymClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = (base_url or mcp_settings.base_url).rstrip("/")
        self._timeout = timeout or mcp_settings.request_timeout
        self._transport = transport

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            follow_redirects=True,
            transport=self._transport,
        )

    async def _request(
        self, method: str, path: str, *, token: str | None = None, **kwargs: Any
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with self._http() as http:
            response = await http.request(method, path, headers=headers, **kwargs)
        if response.is_client_error:
            raise ToolError(
                _api_message(response) or f"{method} {path} failed with HTTP {response.status_code}"
            )
        response.raise_for_status()
        return response

    async def login(self, creds: LoginRequest) -> str:
        response = await self._request(
            "POST", "/api/auth/login", json=creds.model_dump(mode="json")
        )
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
        while True:
            query = {"page": str(page), "page_size": str(_PAGE_SIZE), **(params or {})}
            response = await self._request("GET", path, token=token, params=query)
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
        response = await self._request(
            "POST", "/api/posts", token=token, json=post.model_dump(mode="json")
        )
        return Post.model_validate(response.json())

    @authenticated
    async def get_post(self, token: str, post_id: int) -> Post:
        response = await self._request("GET", f"/api/posts/{post_id}", token=token)
        return Post.model_validate(response.json())

    @authenticated
    async def update_post(self, token: str, post_id: int, edit: PostEdit) -> Post:
        response = await self._request(
            "PATCH",
            f"/api/posts/{post_id}",
            token=token,
            json=edit.model_dump(mode="json", exclude_unset=True),
        )
        return Post.model_validate(response.json())

    @authenticated
    async def publish_post(self, token: str, post_id: int) -> Post:
        response = await self._request(
            "PATCH",
            f"/api/posts/{post_id}",
            token=token,
            json={"status": PostStatus.PUBLISHED.value},
        )
        return Post.model_validate(response.json())

    @authenticated
    async def create_category(self, token: str, category: CategoryCreate) -> Category:
        response = await self._request(
            "POST", "/api/categories", token=token, json=category.model_dump(mode="json")
        )
        return Category.model_validate(response.json())

    @authenticated
    async def list_categories(self, token: str) -> list[Category]:
        response = await self._request("GET", "/api/categories", token=token)
        return [Category.model_validate(row) for row in response.json()]

    @authenticated
    async def create_faq(self, token: str, faq: FaqItem) -> Faq:
        response = await self._request(
            "POST", "/api/faqs", token=token, json=faq.model_dump(mode="json")
        )
        return Faq.model_validate(response.json())

    @authenticated
    async def list_faqs(self, token: str) -> list[Faq]:
        response = await self._request("GET", "/api/faqs", token=token)
        return [Faq.model_validate(row) for row in response.json()]

    @authenticated
    async def list_tags(self, token: str) -> list[Tag]:
        response = await self._request("GET", "/api/tags", token=token)
        return [Tag.model_validate(row) for row in response.json()]

    @authenticated
    async def upload_media(self, token: str, data: bytes, filename: str) -> MediaItem:
        files = {"file": (filename, data, "application/octet-stream")}
        response = await self._request("POST", "/api/media", token=token, files=files)
        return MediaItem.model_validate(response.json())

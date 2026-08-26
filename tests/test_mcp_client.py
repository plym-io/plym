import json
from collections.abc import Callable

import httpx
import pytest
from fastmcp.exceptions import ToolError

from plym.mcp.client import PlymClient
from plym.models.category import CategoryCreate
from plym.models.faq import FaqItem
from plym.models.post import PostCreate, PostEdit
from plym.models.token import LoginRequest

CREDS = LoginRequest(email="editor@plym.local", password="secret")
TOKEN = "token-123"

AUTHOR = {"id": 1, "display_name": "Root", "avatar_url": None, "links": []}
POST_ROW = {
    "id": 7,
    "slug": "hello",
    "path": "/hello",
    "title": "Hello",
    "status": "published",
    "reading_time": 1,
    "content": "hi",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
    "author": AUTHOR,
    "category": None,
    "tags": [],
    "faqs": [],
}

Responder = Callable[[httpx.Request], httpx.Response]


def make_client(respond: Responder) -> PlymClient:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/login":
            assert json.loads(request.content) == CREDS.model_dump(mode="json")
            return httpx.Response(200, json={"access_token": TOKEN})
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        return respond(request)

    return PlymClient(base_url="http://plym.test", transport=httpx.MockTransport(handle))


async def test_publish_post_patches_status() -> None:
    seen = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=POST_ROW)

    post = await make_client(respond).publish_post(CREDS, 7)
    assert seen == {"method": "PATCH", "path": "/api/posts/7", "body": {"status": "published"}}
    assert post.id == 7


async def test_update_post_sends_only_set_fields() -> None:
    seen = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=POST_ROW)

    edit = PostEdit(category_id=3, faqs=[2, 1], tags=["seo"])
    await make_client(respond).update_post(CREDS, 7, edit)
    assert seen["body"] == {"category_id": 3, "faqs": [2, 1], "tags": ["seo"]}


async def test_api_error_message_reaches_the_tool_caller() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        detail = {"code": "posts.slug_conflict", "message": "Slug 'hello' is already in use"}
        return httpx.Response(409, json={"detail": detail})

    with pytest.raises(ToolError, match="Slug 'hello' is already in use"):
        await make_client(respond).create_post(CREDS, PostCreate(title="Hello", slug="hello"))


async def test_client_error_without_detail_still_raises_tool_error() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(413, text="<html>too large</html>")

    with pytest.raises(ToolError, match="POST /api/media failed with HTTP 413"):
        await make_client(respond).upload_media(CREDS, b"bytes", "x.png")


async def test_server_error_stays_loud() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(httpx.HTTPStatusError):
        await make_client(respond).list_faqs(CREDS)


async def test_login_failure_surfaces_api_message() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        detail = {"code": "auth.invalid_credentials", "message": "Invalid email or password"}
        return httpx.Response(401, json={"detail": detail})

    client = PlymClient(base_url="http://plym.test", transport=httpx.MockTransport(handle))
    with pytest.raises(ToolError, match="Invalid email or password"):
        await client.list_categories(CREDS)


async def test_create_faq_and_category_round_trip() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path == "/api/faqs":
            return httpx.Response(201, json={"id": 5, **body})
        return httpx.Response(201, json={"id": 9, "slug": "guides", **body})

    client = make_client(respond)
    faq = await client.create_faq(CREDS, FaqItem(question="Q?", answer="A."))
    category = await client.create_category(CREDS, CategoryCreate(name="Guides"))
    assert (faq.id, faq.question) == (5, "Q?")
    assert (category.id, category.slug) == (9, "guides")


async def test_list_posts_paginates_until_total() -> None:
    pages: list[int] = []

    def respond(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        pages.append(page)
        assert request.url.params["include_drafts"] == "true"
        return httpx.Response(200, json={"items": [POST_ROW], "total": 2, "page": page})

    posts = await make_client(respond).list_posts(CREDS)
    assert pages == [1, 2]
    assert len(posts) == 2

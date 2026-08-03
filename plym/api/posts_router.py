from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import (
    CurrentUser,
    current_user,
    db_session,
    optional_current_user,
    require_editor,
)
from plym.api.state import bundled_css, prism_js, site_config
from plym.config.site import SiteConfig
from plym.exceptions.auth import InsufficientRoleError
from plym.exceptions.posts import PostNotFoundError
from plym.models.common import PostStatus, Role
from plym.models.post import (
    Post,
    PostCreate,
    PostListItem,
    PostUpdate,
    PreviewRequest,
    PreviewResponse,
)
from plym.service.post_service import PostService

router = APIRouter(prefix="/api/posts", tags=["Posts"])


class PostPage(BaseModel):
    items: list[PostListItem]
    total: int
    page: int
    page_size: int


def _service(
    session: AsyncSession = Depends(db_session),
    site: SiteConfig = Depends(site_config),
    css: str = Depends(bundled_css),
    prism: str = Depends(prism_js),
) -> PostService:
    return PostService(session, site, css, prism)


def _is_editor(user: CurrentUser | None) -> bool:
    return user is not None and user.role in (Role.EDITOR, Role.ADMINISTRATOR)


@router.get("", response_model=PostPage)
async def list_posts(
    page: int = Query(1, ge=1),
    page_size: int | None = Query(None, ge=1, le=200),
    include_drafts: bool = Query(False, description="Editor+ required when true"),
    status: PostStatus | None = Query(None),
    search: str | None = Query(None, min_length=1, max_length=120),
    site: SiteConfig = Depends(site_config),
    user: CurrentUser | None = Depends(optional_current_user),
    service: PostService = Depends(_service),
) -> PostPage:
    admin_scope = include_drafts or status is not None or search is not None
    if admin_scope and not _is_editor(user):
        raise InsufficientRoleError()
    size = page_size or site.pagination.page_size
    if admin_scope:
        items, total = await service.list_all(
            page=page, page_size=size, status=status, search=search
        )
    else:
        items, total = await service.list_published(page=page, page_size=size)
    return PostPage(items=items, total=total, page=page, page_size=size)


@router.get("/{post_id}", response_model=Post)
async def get_post(
    post_id: int,
    user: CurrentUser | None = Depends(optional_current_user),
    service: PostService = Depends(_service),
) -> Post:
    post = await service.get(post_id)
    if post.status != PostStatus.PUBLISHED and not _is_editor(user):
        raise PostNotFoundError()
    return post


@router.post("", response_model=Post, status_code=201, dependencies=[Depends(require_editor)])
async def create_post(
    payload: PostCreate,
    user: CurrentUser = Depends(current_user),
    service: PostService = Depends(_service),
) -> Post:
    return await service.create(user.id, payload)


@router.patch("/{post_id}", response_model=Post, dependencies=[Depends(require_editor)])
async def update_post(
    post_id: int,
    payload: PostUpdate,
    service: PostService = Depends(_service),
) -> Post:
    return await service.update(post_id, payload)


@router.post("/{post_id}/refresh", response_model=Post, dependencies=[Depends(require_editor)])
async def refresh_post(post_id: int, service: PostService = Depends(_service)) -> Post:
    return await service.refresh(post_id)


@router.delete("/{post_id}", status_code=204, dependencies=[Depends(require_editor)])
async def delete_post(post_id: int, service: PostService = Depends(_service)) -> None:
    await service.delete(post_id)


@router.post("/preview", response_model=PreviewResponse, dependencies=[Depends(require_editor)])
async def preview_post(
    payload: PreviewRequest, service: PostService = Depends(_service)
) -> PreviewResponse:
    html = service.preview(
        title=payload.title,
        content=payload.content,
        excerpt=payload.excerpt,
        cover=payload.cover,
        canonical_url=payload.canonical_url,
    )
    return PreviewResponse(html=html)

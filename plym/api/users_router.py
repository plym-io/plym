from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import CurrentUser, current_user, db_session, require_admin
from plym.api.state import bundled_css, prism_js, site_config
from plym.config.site import SiteConfig
from plym.models.user import AdminPasswordReset, User, UserCreate, UserRoleUpdate, UserUpdate
from plym.repository.user_repository import UserRepository
from plym.service.auth_service import AuthService
from plym.service.user_service import UserService

router = APIRouter(prefix="/api/users", tags=["Users"])


def _service(
    session: AsyncSession = Depends(db_session),
    site: SiteConfig = Depends(site_config),
    css: str = Depends(bundled_css),
    prism: str = Depends(prism_js),
) -> UserService:
    return UserService(session, site, css, prism)


class UserPage(BaseModel):
    items: list[User]
    total: int
    page: int
    page_size: int


@router.get("", response_model=UserPage, dependencies=[Depends(current_user)])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(db_session),
) -> UserPage:
    repo = UserRepository(session)
    rows = await repo.list_paginated(limit=page_size, offset=(page - 1) * page_size)
    total = int(rows[0]["total"]) if rows else await repo.count()
    return UserPage(
        items=[User.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/me", response_model=User)
async def me(
    user: CurrentUser = Depends(current_user),
    service: UserService = Depends(_service),
) -> User:
    return await service.get(user.id)


@router.patch("/me", response_model=User)
async def update_me(
    payload: UserUpdate,
    user: CurrentUser = Depends(current_user),
    service: UserService = Depends(_service),
) -> User:
    return await service.update_profile(
        user.id,
        display_name=payload.display_name,
        bio=payload.bio,
        avatar_url=payload.avatar_url,
        links=payload.links,
    )


@router.post("", response_model=User, status_code=201, dependencies=[Depends(require_admin)])
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(db_session),
    service: UserService = Depends(_service),
) -> User:
    auth = AuthService(session)
    user_id = await auth.register(
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        role=payload.role.value,
    )
    return await service.get(user_id)


@router.post(
    "/{user_id}/reset-password",
    dependencies=[Depends(require_admin)],
)
async def admin_reset_password(
    user_id: int,
    payload: AdminPasswordReset,
    session: AsyncSession = Depends(db_session),
) -> dict[str, bool]:
    await AuthService(session).admin_reset_password(user_id, payload.new_password)
    return {"ok": True}


@router.patch("/{user_id}/role", response_model=User)
async def change_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    requester: CurrentUser = Depends(require_admin),
    service: UserService = Depends(_service),
) -> User:
    return await service.change_role(user_id, payload.role, requester_id=requester.id)


@router.delete("/{user_id}/deactivate", status_code=204)
async def deactivate_user(
    user_id: int,
    requester: CurrentUser = Depends(require_admin),
    service: UserService = Depends(_service),
) -> None:
    await service.deactivate(user_id, requester_id=requester.id)


@router.post(
    "/{user_id}/reactivate",
    response_model=User,
    dependencies=[Depends(require_admin)],
)
async def reactivate_user(
    user_id: int,
    service: UserService = Depends(_service),
) -> User:
    return await service.reactivate(user_id)

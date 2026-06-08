from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import CurrentUser, current_user, db_session
from plym.models.token import LoginRequest, RefreshRequest, TokenPair
from plym.models.user import PasswordChange
from plym.service.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, session: AsyncSession = Depends(db_session)) -> TokenPair:
    return await AuthService(session).login(payload.email, payload.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, session: AsyncSession = Depends(db_session)) -> TokenPair:
    return await AuthService(session).refresh(payload.refresh_token)


@router.post("/logout")
async def logout(
    payload: RefreshRequest, session: AsyncSession = Depends(db_session)
) -> dict[str, bool]:
    await AuthService(session).logout(payload.refresh_token)
    return {"ok": True}


@router.post("/change-password")
async def change_password(
    payload: PasswordChange,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, bool]:
    await AuthService(session).change_password(user.id, payload.old_password, payload.new_password)
    return {"ok": True}

from collections.abc import AsyncIterator, Callable

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from plym.db.session import get_session_factory
from plym.exceptions.auth import InsufficientRoleError, TokenInvalidError
from plym.models.common import Role
from plym.service.token_service import TokenService

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="JWT",
    description="Paste the access token returned by POST /api/auth/login",
)


async def db_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


class CurrentUser:
    def __init__(self, user_id: int, role: Role) -> None:
        self.id = user_id
        self.role = role


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise TokenInvalidError()
    try:
        payload = TokenService().decode_access(credentials.credentials)
    except Exception as e:
        raise TokenInvalidError() from e
    if payload.get("typ") != "access":
        raise TokenInvalidError()
    return CurrentUser(user_id=int(payload["sub"]), role=Role(payload["role"]))


async def optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> CurrentUser | None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        payload = TokenService().decode_access(credentials.credentials)
    except Exception:
        return None
    if payload.get("typ") != "access":
        return None
    return CurrentUser(user_id=int(payload["sub"]), role=Role(payload["role"]))


def require_role(*roles: Role) -> Callable[[CurrentUser], CurrentUser]:
    allowed = set(roles)

    def _checker(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise InsufficientRoleError()
        return user

    return _checker


require_editor = require_role(Role.EDITOR, Role.ADMINISTRATOR)
require_admin = require_role(Role.ADMINISTRATOR)

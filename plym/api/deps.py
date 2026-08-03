from collections.abc import AsyncIterator, Callable

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from plym.db.session import get_session_factory
from plym.exceptions.auth import InsufficientRoleError, TokenInvalidError
from plym.models.common import Role
from plym.repository.user_repository import UserRepository
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


# Access tokens are stateless, so role and activation are re-read from the database on
# every request: a deactivated or demoted account must lose access immediately, not when
# its access token happens to expire.
async def _authenticate(
    credentials: HTTPAuthorizationCredentials | None, session: AsyncSession
) -> CurrentUser | None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        payload = TokenService().decode_access(credentials.credentials)
        if payload.get("typ") != "access":
            return None
        user_id = int(payload["sub"])
    except Exception:
        return None
    row = await UserRepository(session).get_by_id(user_id)
    if not row or not row["is_active"]:
        return None
    return CurrentUser(user_id=row["id"], role=Role(row["role"]))


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    session: AsyncSession = Depends(db_session),
) -> CurrentUser:
    user = await _authenticate(credentials, session)
    if user is None:
        raise TokenInvalidError()
    return user


async def optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    session: AsyncSession = Depends(db_session),
) -> CurrentUser | None:
    return await _authenticate(credentials, session)


def require_role(*roles: Role) -> Callable[[CurrentUser], CurrentUser]:
    allowed = set(roles)

    def _checker(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise InsufficientRoleError()
        return user

    return _checker


require_editor = require_role(Role.EDITOR, Role.ADMINISTRATOR)
require_admin = require_role(Role.ADMINISTRATOR)

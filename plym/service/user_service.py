from sqlalchemy.ext.asyncio import AsyncSession

from plym.exceptions.users import CannotDeleteSelfError, UserNotFoundError
from plym.instrumentation.tracer import Traced
from plym.models.user import ExtLink, User
from plym.repository.token_repository import RefreshTokenRepository
from plym.repository.user_repository import UserRepository


class UserService(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)

    async def get(self, user_id: int) -> User:
        row = await self._users.get_by_id(user_id)
        if not row:
            raise UserNotFoundError()
        return User.model_validate(row)

    async def update_profile(
        self,
        user_id: int,
        *,
        display_name: str | None,
        bio: str | None,
        avatar_url: str | None,
        links: list[ExtLink] | None,
    ) -> User:
        await self._users.update_profile(
            user_id,
            display_name=display_name,
            bio=bio,
            avatar_url=avatar_url,
            links=[link.model_dump() for link in links] if links is not None else None,
        )
        await self._session.commit()
        return await self.get(user_id)

    async def deactivate(self, user_id: int, *, requester_id: int) -> None:
        if not await self._users.get_by_id(user_id):
            raise UserNotFoundError()
        if user_id == requester_id:
            raise CannotDeleteSelfError()
        await self._users.set_active(user_id, False)
        await self._tokens.delete_all_for_user(user_id)
        await self._session.commit()

    async def reactivate(self, user_id: int) -> User:
        if not await self._users.get_by_id(user_id):
            raise UserNotFoundError()
        await self._users.set_active(user_id, True)
        await self._session.commit()
        return await self.get(user_id)

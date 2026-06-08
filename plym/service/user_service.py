from sqlalchemy.ext.asyncio import AsyncSession

from plym.exceptions.users import UserNotFoundError
from plym.models.user import User
from plym.repository.user_repository import UserRepository


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

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
    ) -> User:
        await self._users.update_profile(
            user_id,
            display_name=display_name,
            bio=bio,
            avatar_url=avatar_url,
        )
        await self._session.commit()
        return await self.get(user_id)

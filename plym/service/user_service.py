import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from plym.config.site import SiteConfig
from plym.exceptions.users import CannotDeleteSelfError, UserNotFoundError
from plym.instrumentation.tracer import Traced
from plym.models.user import ExtLink, User
from plym.repository.post_repository import PostRepository
from plym.repository.token_repository import RefreshTokenRepository
from plym.repository.user_repository import UserRepository
from plym.service.post_pipeline import PostPipeline
from plym.service.search_index_service import SearchIndexService

log = logging.getLogger("plym.users")

_RENDER_CHUNK = 200


def _rendered_identity(user: User) -> dict[str, Any]:
    return user.model_dump(include={"display_name", "avatar_url", "links"})


class UserService(Traced):
    def __init__(self, session: AsyncSession, site: SiteConfig, css: str, prism_js: str) -> None:
        self._session = session
        self._site = site
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)
        self._posts = PostRepository(session)
        self._pipeline = PostPipeline(site, css, prism_js)

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
        before = await self.get(user_id)
        await self._users.update_profile(
            user_id,
            display_name=display_name,
            bio=bio,
            avatar_url=avatar_url,
            links=[link.model_dump() for link in links] if links is not None else None,
        )
        await self._session.commit()
        after = await self.get(user_id)

        if _rendered_identity(before) != _rendered_identity(after):
            self._pipeline.invalidate_index()
            await self._rerender_authored_posts(user_id)
            if before.display_name != after.display_name:
                await SearchIndexService(self._session, self._site).refresh()
        return after

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

    async def _rerender_authored_posts(self, user_id: int) -> None:
        after = 0
        while True:
            rows = await self._posts.list_published_full_after(
                after=after, limit=_RENDER_CHUNK, author_id=user_id
            )
            if not rows:
                return
            for row in rows:
                try:
                    await self._pipeline.render_row(row)
                except Exception:
                    log.exception("failed to re-render %s after a profile change", row["slug"])
            after = rows[-1]["id"]
            if len(rows) < _RENDER_CHUNK:
                return

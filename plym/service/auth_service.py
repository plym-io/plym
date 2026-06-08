from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from plym.exceptions.auth import (
    InactiveUserError,
    InvalidCredentialsError,
    TokenInvalidError,
)
from plym.exceptions.users import EmailAlreadyExistsError, UserNotFoundError
from plym.instrumentation.decorators import instrumented
from plym.models.token import TokenPair
from plym.repository.token_repository import RefreshTokenRepository
from plym.repository.user_repository import UserRepository
from plym.service.password_service import PasswordService
from plym.service.token_service import TokenService


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)
        self._passwords = PasswordService()
        self._jwt = TokenService()

    @instrumented("users.create", audit=True)
    async def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        role: str,
    ) -> int:
        if await self._users.exists_by_email(email):
            raise EmailAlreadyExistsError()
        password_hash = self._passwords.hash(password)
        user_id = await self._users.create(
            email=email,
            password_hash=password_hash,
            role=role,
            display_name=display_name,
        )
        await self._session.commit()
        return user_id

    @instrumented("auth.login", audit=True)
    async def login(self, email: str, password: str) -> TokenPair:
        user = await self._users.get_by_email(email)
        if not user:
            raise InvalidCredentialsError()
        if not self._passwords.verify(user["password_hash"], password):
            raise InvalidCredentialsError()
        if not user["is_active"]:
            raise InactiveUserError()
        if self._passwords.needs_rehash(user["password_hash"]):
            await self._users.update_password(user["id"], self._passwords.hash(password))
        return await self._issue_pair(user["id"], user["role"])

    @instrumented("auth.refresh")
    async def refresh(self, raw_token: str) -> TokenPair:
        token_hash = self._jwt.hash_refresh(raw_token)
        record = await self._tokens.get_by_hash(token_hash)
        if not record:
            raise TokenInvalidError()
        expires_at = record["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise TokenInvalidError()
        await self._tokens.delete_by_id(record["id"])
        user = await self._users.get_by_id(record["user_id"])
        if not user or not user["is_active"]:
            raise InactiveUserError()
        return await self._issue_pair(user["id"], user["role"])

    @instrumented("auth.logout", audit=True)
    async def logout(self, raw_token: str) -> None:
        record = await self._tokens.get_by_hash(self._jwt.hash_refresh(raw_token))
        if record:
            await self._tokens.delete_by_id(record["id"])
            await self._session.commit()

    @instrumented("auth.password_change", audit=True)
    async def change_password(self, user_id: int, old: str, new: str) -> None:
        user = await self._users.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()
        if not self._passwords.verify(user["password_hash"], old):
            raise InvalidCredentialsError()
        await self._users.update_password(user_id, self._passwords.hash(new))
        await self._tokens.delete_all_for_user(user_id)
        await self._session.commit()

    @instrumented("auth.admin_reset_password", audit=True)
    async def admin_reset_password(self, user_id: int, new: str) -> None:
        user = await self._users.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()
        await self._users.update_password(user_id, self._passwords.hash(new))
        await self._tokens.delete_all_for_user(user_id)
        await self._session.commit()

    async def _issue_pair(self, user_id: int, role: str) -> TokenPair:
        access = self._jwt.issue_access(user_id, role)
        raw, token_hash, expires_at = self._jwt.generate_refresh()
        await self._tokens.insert(user_id, token_hash, expires_at)
        await self._session.commit()
        return TokenPair(access_token=access, refresh_token=raw)

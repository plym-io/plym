from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plym.instrumentation.tracer import Traced


class RefreshTokenRepository(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, user_id: int, token_hash: str, expires_at: datetime) -> int:
        result = await self._session.execute(
            text(
                """
                INSERT INTO auth.refresh_tokens (user_id, token_hash, expires_at)
                VALUES (:user_id, :token_hash, :expires_at)
                RETURNING id
                """
            ),
            {"user_id": user_id, "token_hash": token_hash, "expires_at": expires_at},
        )
        return int(result.scalar_one())

    async def get_by_hash(self, token_hash: str) -> dict | None:
        result = await self._session.execute(
            text(
                """
                SELECT id, user_id, token_hash, expires_at
                FROM auth.refresh_tokens
                WHERE token_hash = :token_hash
                """
            ),
            {"token_hash": token_hash},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def consume_by_hash(self, token_hash: str) -> dict | None:
        result = await self._session.execute(
            text(
                """
                DELETE FROM auth.refresh_tokens
                WHERE token_hash = :token_hash
                RETURNING id, user_id, expires_at
                """
            ),
            {"token_hash": token_hash},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def delete_by_id(self, token_id: int) -> None:
        await self._session.execute(
            text("DELETE FROM auth.refresh_tokens WHERE id = :id"),
            {"id": token_id},
        )

    async def delete_all_for_user(self, user_id: int) -> None:
        await self._session.execute(
            text("DELETE FROM auth.refresh_tokens WHERE user_id = :id"),
            {"id": user_id},
        )

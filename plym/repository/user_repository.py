from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plym.instrumentation.tracer import Traced


class UserRepository(Traced):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> dict | None:
        result = await self._session.execute(
            text(
                """
                SELECT u.id, u.email, u.password_hash, u.role, u.is_active,
                       u.created_at, u.updated_at,
                       p.display_name, p.bio, p.avatar_url
                FROM auth.users u
                LEFT JOIN public.pl_users p ON p.id = u.id
                WHERE u.email = :email
                """
            ),
            {"email": email},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_by_id(self, user_id: int) -> dict | None:
        result = await self._session.execute(
            text(
                """
                SELECT u.id, u.email, u.password_hash, u.role, u.is_active,
                       u.created_at, u.updated_at,
                       p.display_name, p.bio, p.avatar_url
                FROM auth.users u
                LEFT JOIN public.pl_users p ON p.id = u.id
                WHERE u.id = :id
                """
            ),
            {"id": user_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def exists_by_email(self, email: str) -> bool:
        result = await self._session.execute(
            text("SELECT 1 FROM auth.users WHERE email = :email"),
            {"email": email},
        )
        return result.first() is not None

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        role: str,
        display_name: str,
    ) -> int:
        result = await self._session.execute(
            text(
                """
                INSERT INTO auth.users (email, password_hash, role)
                VALUES (:email, :password_hash, :role)
                RETURNING id
                """
            ),
            {"email": email, "password_hash": password_hash, "role": role},
        )
        user_id = int(result.scalar_one())
        await self._session.execute(
            text(
                """
                INSERT INTO public.pl_users (id, display_name)
                VALUES (:id, :display_name)
                """
            ),
            {"id": user_id, "display_name": display_name},
        )
        return user_id

    async def update_password(self, user_id: int, password_hash: str) -> None:
        await self._session.execute(
            text("UPDATE auth.users SET password_hash = :h WHERE id = :id"),
            {"h": password_hash, "id": user_id},
        )

    async def list_paginated(self, *, limit: int, offset: int) -> list[dict]:
        result = await self._session.execute(
            text(
                """
                SELECT u.id, u.email, u.role, u.is_active,
                       u.created_at, u.updated_at,
                       p.display_name, p.bio, p.avatar_url
                FROM auth.users u
                LEFT JOIN public.pl_users p ON p.id = u.id
                ORDER BY u.created_at DESC, u.id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        )
        return [dict(r) for r in result.mappings().all()]

    async def count(self) -> int:
        result = await self._session.execute(text("SELECT COUNT(*) FROM auth.users"))
        return int(result.scalar_one())

    async def update_profile(
        self,
        user_id: int,
        *,
        display_name: str | None = None,
        bio: str | None = None,
        avatar_url: str | None = None,
    ) -> None:
        await self._session.execute(
            text(
                """
                UPDATE public.pl_users
                SET display_name = COALESCE(:display_name, display_name),
                    bio = COALESCE(:bio, bio),
                    avatar_url = COALESCE(:avatar_url, avatar_url)
                WHERE id = :id
                """
            ),
            {"display_name": display_name, "bio": bio, "avatar_url": avatar_url, "id": user_id},
        )

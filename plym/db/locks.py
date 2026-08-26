from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_CLAIM_SLUG = text("SELECT pg_advisory_xact_lock(hashtext('plym.slug:' || :slug))")


async def claim_slug(session: AsyncSession, slug: str) -> None:
    await session.execute(_CLAIM_SLUG, {"slug": slug})

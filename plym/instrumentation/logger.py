from contextvars import ContextVar
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from plym.repository.log_repository import LogRepository

_current_actor: ContextVar[int | None] = ContextVar("plym_actor", default=None)


def set_actor(actor_id: int | None) -> None:
    _current_actor.set(actor_id)


def get_actor() -> int | None:
    return _current_actor.get()


async def write_log(
    session: AsyncSession,
    *,
    event: str,
    target: str | None,
    payload: dict[str, Any],
    audit: bool,
) -> None:
    await LogRepository(session).insert(
        event=event,
        actor_id=get_actor(),
        target=target,
        payload=payload,
        audit=audit,
    )

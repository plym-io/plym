from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from plym.instrumentation.logger import write_log

P = ParamSpec("P")
R = TypeVar("R")


def _find_session(args: tuple[Any, ...], kwargs: dict[str, Any]) -> AsyncSession | None:
    for value in (*args, *kwargs.values()):
        if isinstance(value, AsyncSession):
            return value
        session = getattr(value, "_session", None)
        if isinstance(session, AsyncSession):
            return session
    return None


def instrumented(
    event: str,
    *,
    audit: bool = False,
    target: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            session = _find_session(args, kwargs)
            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                if session is not None:
                    await write_log(
                        session,
                        event=f"{event}.error",
                        target=target,
                        payload={"error": type(exc).__name__, "message": str(exc)[:512]},
                        audit=audit,
                    )
                    await session.commit()
                raise
            if session is not None:
                await write_log(
                    session,
                    event=event,
                    target=target,
                    payload={},
                    audit=audit,
                )
                await session.commit()
            return result

        return wrapper

    return decorator

import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from plym.instrumentation.context import current_request_id, get_actor
from plym.repository.audit_repository import AuditRepository

P = ParamSpec("P")
R = TypeVar("R")

Capture = Callable[[dict[str, Any], Any], Any]


def _find_session(args: tuple[Any, ...], kwargs: dict[str, Any]) -> AsyncSession | None:
    for value in (*args, *kwargs.values()):
        if isinstance(value, AsyncSession):
            return value
        session = getattr(value, "_session", None)
        if isinstance(session, AsyncSession):
            return session
    return None


def audit(
    event: str,
    *,
    target: Capture | None = None,
    payload: Capture | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Record a business fact ('who did what to what') to public.pl_audit on success only.
    `target`/`payload` are callables of (named_args, result). Errors are a tracing concern and are
    never written here."""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        sig = inspect.signature(func)

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            result = await func(*args, **kwargs)
            session = _find_session(args, kwargs)
            if session is not None:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                params = dict(bound.arguments)
                params.pop("self", None)
                tgt = target(params, result) if target else None
                body = payload(params, result) if payload else {}
                await AuditRepository(session).insert(
                    event=event,
                    actor_id=get_actor(),
                    target=str(tgt) if tgt is not None else None,
                    payload=body,
                    request_id=current_request_id(),
                )
                await session.commit()
            return result

        return wrapper

    return decorator

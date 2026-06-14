import inspect
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any

from opentelemetry.trace import Status, StatusCode

from plym.instrumentation.telemetry import get_tracer
from plym.settings import settings

_REDACTED = "***"
_SECRET_HINTS = ("password", "token", "secret", "authorization", "hash", "data", "credential")


def _safe(name: str, value: Any) -> Any:
    lowered = name.lower()
    if any(hint in lowered for hint in _SECRET_HINTS):
        return _REDACTED
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return type(value).__name__


def _attach_args(span, sig: inspect.Signature, args: tuple, kwargs: dict) -> None:
    try:
        bound = sig.bind(*args, **kwargs)
    except TypeError:
        return
    for key, value in bound.arguments.items():
        if key == "self":
            continue
        span.set_attribute(f"plym.arg.{key}", str(_safe(key, value)))


def _wrap[**P, R](span_name: str, func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    sig = inspect.signature(func)

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with get_tracer().start_as_current_span(span_name) as span:
            if settings.trace_args:
                _attach_args(span, sig, args, kwargs)
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                raise

    return wrapper


class Traced:
    """Auto-instruments every public async method of subclasses with a timed span."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for name, attr in list(vars(cls).items()):
            if name.startswith("_") or not inspect.iscoroutinefunction(attr):
                continue
            setattr(cls, name, _wrap(f"{cls.__name__}.{name}", attr))


def traced[**P, R](
    name: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        return _wrap(name or func.__qualname__, func)

    return decorator


@asynccontextmanager
async def span(name: str, **attributes: Any):
    with get_tracer().start_as_current_span(name) as current:
        for key, value in attributes.items():
            current.set_attribute(key, value)
        yield current

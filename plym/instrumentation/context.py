from contextvars import ContextVar

from opentelemetry import trace

_current_actor: ContextVar[int | None] = ContextVar("plym_actor", default=None)


def set_actor(actor_id: int | None) -> None:
    _current_actor.set(actor_id)


def get_actor() -> int | None:
    return _current_actor.get()


def current_request_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return trace.format_trace_id(ctx.trace_id)

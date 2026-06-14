import sys
from collections import defaultdict

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanProcessor
from opentelemetry.trace import StatusCode

from plym.settings import settings

_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_MAGENTA = "\033[35m"

_MAX_BUFFERED = 10_000


def _color_enabled() -> bool:
    if settings.trace_color is not None:
        return settings.trace_color
    return sys.stdout.isatty()


class TreeSpanProcessor(SpanProcessor):
    """Buffers the spans of a trace and prints them as a timed call-tree once the root span ends."""

    def __init__(self) -> None:
        self._spans: dict[int, list[ReadableSpan]] = defaultdict(list)

    def on_start(self, span, parent_context=None) -> None:  # noqa: ARG002
        return None

    def on_end(self, span: ReadableSpan) -> None:
        trace_id = span.context.trace_id
        bucket = self._spans[trace_id]
        bucket.append(span)
        if span.parent is None or span.parent.trace_id != trace_id:
            self._flush(trace_id)
        elif len(bucket) > _MAX_BUFFERED:
            self._spans.pop(trace_id, None)

    def shutdown(self) -> None:
        for trace_id in list(self._spans):
            self._flush(trace_id)

    def force_flush(self, timeout_millis: int = 30_000) -> bool:  # noqa: ARG002
        return True

    def _flush(self, trace_id: int) -> None:
        spans = self._spans.pop(trace_id, [])
        if not spans:
            return
        children: dict[int, list[ReadableSpan]] = defaultdict(list)
        ids = {s.context.span_id for s in spans}
        roots: list[ReadableSpan] = []
        for s in spans:
            if s.parent is not None and s.parent.span_id in ids:
                children[s.parent.span_id].append(s)
            else:
                roots.append(s)
        lines: list[str] = []
        for root in sorted(roots, key=lambda s: s.start_time):
            self._render(root, children, "", True, lines, 0)
            lines.append("")
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()

    def _render(self, span, children, prefix, is_last, lines, depth) -> None:
        if depth == 0:
            lines.append(self._header(span))
            child_prefix = ""
        else:
            connector = "└─ " if is_last else "├─ "
            lines.append(prefix + self._c(_DIM, connector) + self._label(span))
            child_prefix = prefix + ("   " if is_last else self._c(_DIM, "│  "))
        kids = sorted(children.get(span.context.span_id, []), key=lambda s: s.start_time)
        for i, kid in enumerate(kids):
            self._render(kid, children, child_prefix, i == len(kids) - 1, lines, depth + 1)

    def _header(self, span) -> str:
        attrs = span.attributes or {}
        actor = attrs.get("plym.actor_id")
        trace_hex = format(span.context.trace_id, "032x")[:8]
        bits = [self._c(_BOLD + _CYAN, self._name(span))]
        if actor is not None:
            bits.append(self._c(_DIM, f"actor={actor}"))
        bits.append(self._c(_DIM, f"trace={trace_hex}"))
        status = attrs.get("http.response.status_code") or attrs.get("http.status_code")
        if status is not None:
            bits.append(self._status_code(int(status)))
        bits.append(self._duration(span))
        return "■ " + "  ".join(bits)

    def _label(self, span) -> str:
        color = _RED if span.status.status_code is StatusCode.ERROR else None
        name = self._c(color, self._name(span)) if color else self._name(span)
        return f"{name}  {self._duration(span)}{self._error_suffix(span)}"

    def _name(self, span) -> str:
        attrs = span.attributes or {}
        method = attrs.get("http.request.method") or attrs.get("http.method")
        if method:
            route = (
                attrs.get("http.route")
                or attrs.get("url.path")
                or attrs.get("http.target")
                or ""
            )
            return f"{method} {route}".strip()
        statement = attrs.get("db.statement")
        if statement:
            flat = " ".join(str(statement).split())
            return self._c(_MAGENTA, flat[:80])
        return span.name

    def _duration(self, span) -> str:
        ms = (span.end_time - span.start_time) / 1_000_000
        text = f"{ms:.1f}ms"
        if ms >= settings.trace_slow_ms:
            return self._c(_YELLOW, f"{text} ⚠ slow")
        return self._c(_DIM, text)

    def _status_code(self, status: int) -> str:
        color = _GREEN if status < 400 else _RED
        return self._c(color, str(status))

    def _error_suffix(self, span) -> str:
        if span.status.status_code is not StatusCode.ERROR:
            return ""
        for event in span.events:
            if event.name == "exception":
                kind = event.attributes.get("exception.type", "error")
                return self._c(_RED, f"  ✗ {kind}")
        return self._c(_RED, "  ✗")

    def _c(self, color, text) -> str:
        if not color or not _color_enabled():
            return text
        return f"{color}{text}{_RESET}"

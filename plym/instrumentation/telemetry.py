import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
from opentelemetry.trace import Tracer

from plym.instrumentation.console_exporter import TreeSpanProcessor
from plym.settings import settings

_CONFIGURED = False
_tracer: Tracer | None = None


class _TraceContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        ctx = trace.get_current_span().get_span_context()
        record.trace_id = format(ctx.trace_id, "032x")[:8] if ctx.is_valid else "--------"
        return True


def _build_processors() -> list:
    processors = []
    for name in (p.strip() for p in settings.trace_exporter.split(",")):
        if name == "console":
            processors.append(TreeSpanProcessor())
        elif name == "otlp":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint, insecure=True)
            processors.append(BatchSpanProcessor(exporter))
    return processors


def configure_telemetry() -> None:
    """Set up tracing (console call-tree by default, OTLP when configured) and route plym's own
    stdlib logs to the console with trace correlation. Idempotent — safe to call on reload."""
    global _CONFIGURED, _tracer
    if _CONFIGURED:
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.service_name}),
        sampler=ParentBasedTraceIdRatio(settings.trace_sample),
    )
    for processor in _build_processors():
        provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    _tracer = provider.get_tracer("plym")

    level = logging.DEBUG if settings.debug else logging.INFO
    handler = logging.StreamHandler()
    handler.addFilter(_TraceContextFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(trace_id)s %(name)s | %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("plym").setLevel(level)

    _CONFIGURED = True


def get_tracer() -> Tracer:
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer("plym")
    return _tracer

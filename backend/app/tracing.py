"""OpenTelemetry tracing. Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set; then
spans go out over OTLP/HTTP (Tempo in compose, any OTLP backend elsewhere).

A question becomes one trace: the HTTP request, the embedding + example
search, both model calls, the DuckDB query and every SQL statement against
Postgres. An upload's trace continues on the worker — the trace context
travels with the job.
"""
import logging
import os
from contextlib import contextmanager
from opentelemetry import propagate, trace

log = logging.getLogger(__name__)

ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
tracer = trace.get_tracer("insightiq")

_provider = None

def setup(service_name: str, app=None):
    """Install the tracer provider and auto-instrumentation. Safe to call when tracing is off."""
    global _provider
    if not ENDPOINT or _provider is not None:
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from app.db import engine

    service = os.getenv("OTEL_SERVICE_NAME", service_name)
    _provider = TracerProvider(resource=Resource.create({"service.name": service}))
    _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(_provider)

    _trace_sql(engine)
    HTTPXClientInstrumentor().instrument()          # the Groq client is httpx underneath
    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready")
    log.info("tracing to %s as %s", ENDPOINT, service)

def _trace_sql(engine):
    """A span per SQL statement against the metadata database. (The upstream
    SQLAlchemy instrumentor doesn't support SQLAlchemy 2.1 yet; these are the
    same engine events it hooks.)"""
    from sqlalchemy import event

    @event.listens_for(engine, "before_cursor_execute")
    def _start(conn, cursor, statement, parameters, context, executemany):
        op = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else "SQL"
        span = tracer.start_span(f"db {op}", kind=trace.SpanKind.CLIENT, attributes={
            "db.system": engine.dialect.name,
            "db.statement": statement[:1000],
        })
        conn.info.setdefault("_otel_spans", []).append(span)

    def _end(conn, error=None):
        spans = conn.info.get("_otel_spans")
        if spans:
            span = spans.pop()
            if error is not None:
                span.record_exception(error)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
            span.end()

    event.listen(engine, "after_cursor_execute", lambda conn, *a: _end(conn))
    event.listen(engine, "handle_error", lambda ctx: _end(ctx.connection, ctx.original_exception)
                 if ctx.connection is not None else None)

def flush():
    """The worker runs each job in a fork that exits right after — send its spans first."""
    if _provider is not None:
        _provider.force_flush(timeout_millis=5000)

def carrier() -> dict:
    """Current trace context as a dict that can ride along with a job."""
    out: dict = {}
    propagate.inject(out)
    return out

@contextmanager
def continued(carrier: dict | None, name: str, **attributes):
    """A span that continues the trace in `carrier` (or starts one)."""
    ctx = propagate.extract(carrier or {})
    with tracer.start_as_current_span(name, context=ctx, attributes=attributes) as span:
        yield span

def ids() -> tuple[str, str] | None:
    """(trace_id, span_id) of the current span, hex, or None."""
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")

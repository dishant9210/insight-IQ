"""Metrics, traces and logs. The registry is process-wide, so tests compare
before/after values instead of absolute counts."""
import json
import logging
import pytest
from prometheus_client import REGISTRY, generate_latest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from app import logging_setup, metrics, tracing
from app.services import llm_service, rate_limit
from tests.conftest import upload, SALES_CSV, FakeChain

def value(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0

class FakeMessage:
    def __init__(self, content, inp, out):
        self.content = content
        self.usage_metadata = {"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}

def ask(client, dataset_id, question="q"):
    return client.post("/api/query", json={"dataset_id": dataset_id, "question": question})

# --- metrics ---------------------------------------------------------------

def test_http_metrics_label_the_route_template(client):
    route = "/api/datasets/{dataset_id}"
    before = value("insightiq_http_requests_total", method="GET", route=route, status="404")
    client.get("/api/datasets/00000000-0000-0000-0000-000000000000")
    assert value("insightiq_http_requests_total", method="GET", route=route, status="404") == before + 1
    before = value("insightiq_http_requests_total", method="GET", route="unmatched", status="404")
    client.get("/no/such/path")
    assert value("insightiq_http_requests_total", method="GET", route="unmatched", status="404") == before + 1

def test_question_metrics(client, sales, monkeypatch):
    monkeypatch.setattr(llm_service, "sql_chain", FakeChain(FakeMessage("SELECT 1 AS n", 120, 9)))
    monkeypatch.setattr(llm_service, "insight_chain", FakeChain(FakeMessage("one", 40, 5)))
    ok, cached = value("insightiq_queries_total", outcome="ok"), value("insightiq_queries_total", outcome="cached")
    sql_in = value("insightiq_llm_tokens_total", step="sql", kind="input")
    ins_out = value("insightiq_llm_tokens_total", step="insight", kind="output")
    hits = value("insightiq_answer_cache_total", result="hit")
    llm_ok = value("insightiq_llm_request_duration_seconds_count", step="sql", outcome="ok")

    assert ask(client, sales["dataset_id"]).json()["result"] == [{"n": 1}]
    assert ask(client, sales["dataset_id"]).json()["cached"] is True

    assert value("insightiq_queries_total", outcome="ok") == ok + 1
    assert value("insightiq_queries_total", outcome="cached") == cached + 1
    assert value("insightiq_llm_tokens_total", step="sql", kind="input") == sql_in + 120
    assert value("insightiq_llm_tokens_total", step="insight", kind="output") == ins_out + 5
    assert value("insightiq_answer_cache_total", result="hit") == hits + 1
    assert value("insightiq_llm_request_duration_seconds_count", step="sql", outcome="ok") == llm_ok + 1

def test_failed_question_counts_its_status(client, sales, fake_llm):
    before = value("insightiq_queries_total", outcome="400")
    fake_llm("SELECT nope FROM data")
    assert ask(client, sales["dataset_id"]).status_code == 400
    assert value("insightiq_queries_total", outcome="400") == before + 1

def test_ingest_metrics(client):
    ready = value("insightiq_ingest_total", format="csv", outcome="ready")
    failed = value("insightiq_ingest_total", format="xlsx", outcome="failed")
    upload(client, "sales.csv", SALES_CSV, "text/csv")
    upload(client, "broken.xlsx", b"nope")
    assert value("insightiq_ingest_total", format="csv", outcome="ready") == ready + 1
    assert value("insightiq_ingest_total", format="xlsx", outcome="failed") == failed + 1

def test_rate_limit_metric(client, monkeypatch):
    monkeypatch.setitem(rate_limit.LIMITS, "upload", [(1, 60)])
    before = value("insightiq_rate_limited_total", limit="upload")
    upload(client, "sales.csv", SALES_CSV, "text/csv")
    assert upload(client, "sales.csv", SALES_CSV, "text/csv").status_code == 429
    assert value("insightiq_rate_limited_total", limit="upload") == before + 1

def test_state_collector_reports_datasets(client, sales):
    metrics.register_state_collector()
    metrics.register_state_collector()       # idempotent
    text = generate_latest(REGISTRY).decode()
    assert 'insightiq_datasets{status="ready"}' in text

# --- traces ----------------------------------------------------------------

@pytest.fixture(scope="module")
def spans():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter

def test_question_is_one_trace(client, sales, fake_llm, spans):
    spans.clear()
    fake_llm("SELECT 1 AS n")
    with tracing.tracer.start_as_current_span("request"):
        ask(client, sales["dataset_id"], "a fresh question")
    names = {s.name: s for s in spans.get_finished_spans()}
    assert {"request", "retrieve", "llm.sql", "sql.execute", "llm.insight"} <= set(names)
    assert len({s.context.trace_id for s in names.values()}) == 1
    assert names["retrieve"].attributes["retrieval.examples"] == 0
    assert names["llm.sql"].attributes["llm.outcome"] == "ok"

def test_ingest_continues_the_uploads_trace(spans):
    spans.clear()
    with tracing.tracer.start_as_current_span("upload request") as parent:
        carried = tracing.carrier()
    assert "traceparent" in carried
    # later, somewhere else (the worker)
    with tracing.continued(carried, "ingest") as child:
        pass
    assert child.context.trace_id == parent.context.trace_id
    assert child.parent.span_id == parent.context.span_id

# --- logs ------------------------------------------------------------------

def test_json_logs_carry_the_trace_id(spans):
    fmt = logging_setup.JsonFormatter()
    record = logging.LogRecord("insightiq", logging.INFO, __file__, 1, "hello %s", ("there",), None)
    assert "trace_id" not in json.loads(fmt.format(record))
    with tracing.tracer.start_as_current_span("work") as span:
        out = json.loads(fmt.format(record))
    assert out["msg"] == "hello there" and out["level"] == "info"
    assert out["trace_id"] == format(span.get_span_context().trace_id, "032x")

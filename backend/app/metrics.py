"""Prometheus metrics. Served on their own port (METRICS_PORT, default 9091)
so they're never on the public api port.

The worker forks a process per job, so it runs prometheus_client in
multiprocess mode (PROMETHEUS_MULTIPROC_DIR set in its environment) and the
counters a job bumps survive the fork exiting.
"""
import logging
import os
import threading
import time
from prometheus_client import (
    REGISTRY, CollectorRegistry, Counter, Histogram, multiprocess, start_http_server,
)
from prometheus_client.core import GaugeMetricFamily

log = logging.getLogger(__name__)

METRICS_PORT = int(os.getenv("METRICS_PORT", "9091"))   # 0 = don't serve

# --- api -------------------------------------------------------------------

HTTP_REQUESTS = Counter(
    "insightiq_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "insightiq_http_request_duration_seconds", "HTTP request latency", ["method", "route"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30))

QUERIES = Counter(
    "insightiq_queries_total", "Questions, by outcome (ok, cached, or the HTTP error code)", ["outcome"])
QUERY_LATENCY = Histogram(
    "insightiq_query_duration_seconds", "End-to-end time to answer a question", ["cached"],
    buckets=(0.01, 0.1, 0.5, 1, 2, 4, 8, 15, 30))
LLM_LATENCY = Histogram(
    "insightiq_llm_request_duration_seconds", "Language model call latency", ["step", "outcome"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30))
LLM_TOKENS = Counter(
    "insightiq_llm_tokens_total", "Tokens sent to and received from the model", ["step", "kind"])
SQL_LATENCY = Histogram(
    "insightiq_sql_execution_duration_seconds", "DuckDB execution time for generated SQL",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5, 20))
ANSWER_CACHE = Counter("insightiq_answer_cache_total", "Answer cache lookups", ["result"])
RATE_LIMITED = Counter("insightiq_rate_limited_total", "Requests rejected with 429", ["limit"])
FEWSHOT = Histogram(
    "insightiq_fewshot_examples", "Past answers put into each prompt", buckets=(0, 1, 2, 3, 5))
RETRIEVAL_LATENCY = Histogram(
    "insightiq_retrieval_duration_seconds", "Embedding + example search + table selection",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5))
FEEDBACK = Counter("insightiq_feedback_total", "Thumbs up / down", ["helpful"])

# --- ingest (worker, or the api when there's no Redis) ----------------------

INGEST = Counter("insightiq_ingest_total", "Files parsed, by outcome", ["format", "outcome"])
INGEST_LATENCY = Histogram(
    "insightiq_ingest_duration_seconds", "Time to parse an upload into DuckDB", ["format"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600))

class Timer:
    """with Timer() as t: ...; t.seconds"""
    def __enter__(self):
        self._start = time.perf_counter()
        self.seconds = 0.0
        return self

    def __exit__(self, *exc):
        self.seconds = time.perf_counter() - self._start
        return False

class _StateCollector:
    """Read at scrape time: queue depth and datasets by status."""
    def collect(self):
        from sqlalchemy import func, select
        from app.db import SessionLocal, Dataset
        from app.queue import get_queue

        datasets = GaugeMetricFamily("insightiq_datasets", "Datasets by status", labels=["status"])
        try:
            with SessionLocal() as s:
                for status, n in s.execute(select(Dataset.status, func.count()).group_by(Dataset.status)):
                    datasets.add_metric([status], n)
        except Exception as e:
            log.warning("dataset metrics unavailable: %s", e)
        yield datasets

        queue = get_queue()
        if queue is not None:
            depth = GaugeMetricFamily("insightiq_ingest_queue_depth", "Uploads waiting for a worker")
            try:
                depth.add_metric([], queue.count)
                yield depth
            except Exception as e:
                log.warning("queue depth unavailable: %s", e)

_state_registered = False

def register_state_collector():
    global _state_registered
    if not _state_registered:
        REGISTRY.register(_StateCollector())
        _state_registered = True

def serve(port: int = METRICS_PORT):
    """Expose /metrics on its own port. Multiprocess-aware for the worker.

    Binds in a background thread: wsgiref looks up the host's FQDN while
    binding, which can stall for seconds on some networks, and that
    shouldn't hold up api startup."""
    if not port:
        return
    registry = REGISTRY
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)

    def bind():
        try:
            start_http_server(port, registry=registry)
            log.info("metrics on :%d/metrics", port)
        except OSError as e:
            log.error("metrics server failed to start on :%d: %s", port, e)

    threading.Thread(target=bind, name="metrics-bind", daemon=True).start()

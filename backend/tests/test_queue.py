"""Uploads through Redis + a worker. fakeredis stands in for Redis and a
SimpleWorker runs the job in-process; CI also runs the real thing in compose."""
import pytest
from fakeredis import FakeRedis
from rq import Queue, SimpleWorker
from app import queue as queue_module
from tests.conftest import upload, SALES_CSV

@pytest.fixture
def ingest_queue(monkeypatch):
    q = Queue(queue_module.QUEUE_NAME, connection=FakeRedis())
    monkeypatch.setattr(queue_module, "_queue", q)
    return q

def run_worker(q):
    SimpleWorker([q], connection=q.connection).work(burst=True)

def test_upload_is_queued_then_processed(client, ingest_queue, fake_llm):
    r = upload(client, "sales.csv", SALES_CSV, "text/csv")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending" and body["rows"] == 0
    assert ingest_queue.count == 1

    # asking before the worker has run is a clear 409, not a crash
    fake_llm("SELECT 1")
    pending = client.post("/api/query", json={"dataset_id": body["dataset_id"], "question": "q"})
    assert pending.status_code == 409 and "processing" in pending.json()["detail"]

    run_worker(ingest_queue)

    done = client.get(f"/api/datasets/{body['dataset_id']}").json()
    assert done["status"] == "ready" and done["rows"] == 4
    fake_llm("SELECT count(*) AS n FROM data")
    ok = client.post("/api/query", json={"dataset_id": body["dataset_id"], "question": "q"})
    assert ok.status_code == 200 and ok.json()["result"] == [{"n": 4}]

def test_failed_job_is_reported(client, ingest_queue, fake_llm):
    did = upload(client, "broken.xlsx", b"nope").json()["dataset_id"]
    run_worker(ingest_queue)

    meta = client.get(f"/api/datasets/{did}").json()
    assert meta["status"] == "failed" and "Could not parse file" in meta["error"]

    fake_llm("SELECT 1")
    r = client.post("/api/query", json={"dataset_id": did, "question": "q"})
    assert r.status_code == 409 and "failed to load" in r.json()["detail"]

def test_ready_reports_redis(client, ingest_queue):
    assert client.get("/ready").json()["queue"] == "ok"

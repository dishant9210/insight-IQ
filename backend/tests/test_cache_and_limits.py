"""Answer cache and rate limits, on both store backends."""
import pytest
from fakeredis import FakeRedis
from app import store
from app.db import SessionLocal, QueryLog
from app.services import answer_cache, rate_limit
from tests.conftest import upload, SALES_CSV

def ask(client, dataset_id, question="total by name", **kw):
    return client.post("/api/query", json={"dataset_id": dataset_id, "question": question}, **kw)

@pytest.fixture(params=["memory", "redis"])
def any_store(request, monkeypatch):
    s = store.MemoryStore() if request.param == "memory" else store.RedisStore(FakeRedis())
    monkeypatch.setattr(store, "_store", s)
    return s

def test_repeat_question_is_served_from_cache(client, sales, fake_llm, any_store):
    fake_llm("SELECT name, amount FROM data ORDER BY name")
    first = ask(client, sales["dataset_id"])
    assert first.status_code == 200 and first.json()["cached"] is False

    # a fresh chain that records nothing proves the LLM wasn't called again
    chain = fake_llm("SELECT 'wrong' AS x")
    second = ask(client, sales["dataset_id"], "  Total BY name? ")
    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert second.json()["sql"] == first.json()["sql"]
    assert second.json()["result"] == first.json()["result"]
    assert chain.inputs is None

    with SessionLocal() as s:
        assert [r.cached for r in s.query(QueryLog).order_by(QueryLog.id)] == [False, True]

def test_cache_is_per_dataset(client, sales, fake_llm, upload_sales):
    other = upload_sales()
    fake_llm("SELECT 1 AS n")
    ask(client, sales["dataset_id"])
    assert ask(client, other["dataset_id"]).json()["cached"] is False

def test_errors_are_not_cached(client, sales, fake_llm):
    fake_llm("SELECT nope FROM data")
    assert ask(client, sales["dataset_id"]).status_code == 400
    fake_llm("SELECT 1 AS n")
    r = ask(client, sales["dataset_id"])
    assert r.status_code == 200 and r.json()["cached"] is False

def test_cache_can_be_turned_off(client, sales, fake_llm, monkeypatch):
    monkeypatch.setattr(answer_cache, "TTL", 0)
    fake_llm("SELECT 1 AS n")
    ask(client, sales["dataset_id"])
    assert ask(client, sales["dataset_id"]).json()["cached"] is False

class BrokenStore:
    name = "redis"
    def __getattr__(self, _):
        def fail(*a, **kw):
            raise ConnectionError("redis is down")
        return fail

def test_store_outage_fails_open(client, sales, fake_llm, monkeypatch):
    monkeypatch.setattr(store, "_store", BrokenStore())
    fake_llm("SELECT 1 AS n")
    assert ask(client, sales["dataset_id"]).status_code == 200
    assert client.get("/ready").status_code == 503

def test_query_rate_limit(client, sales, fake_llm, any_store, monkeypatch):
    monkeypatch.setitem(rate_limit.LIMITS, "query", [(2, 60)])
    fake_llm("SELECT 1 AS n")
    ok = ask(client, sales["dataset_id"])
    assert ok.headers["X-RateLimit-Limit"] == "2" and ok.headers["X-RateLimit-Remaining"] == "1"
    assert ask(client, sales["dataset_id"]).status_code == 200

    blocked = ask(client, sales["dataset_id"])
    assert blocked.status_code == 429
    assert 0 < int(blocked.headers["Retry-After"]) <= 60
    assert "Too many requests" in blocked.json()["detail"]

def test_tightest_rule_wins(client, sales, fake_llm, monkeypatch):
    monkeypatch.setitem(rate_limit.LIMITS, "query", [(10, 60), (1, 86400)])
    fake_llm("SELECT 1 AS n")
    assert ask(client, sales["dataset_id"]).headers["X-RateLimit-Limit"] == "1"
    assert ask(client, sales["dataset_id"]).status_code == 429

def test_limits_are_per_client(client, sales, fake_llm, monkeypatch):
    monkeypatch.setitem(rate_limit.LIMITS, "query", [(1, 60)])
    monkeypatch.setattr(rate_limit, "CLIENT_IP_HEADER", "Fly-Client-IP")
    fake_llm("SELECT 1 AS n")
    assert ask(client, sales["dataset_id"], headers={"Fly-Client-IP": "1.1.1.1"}).status_code == 200
    assert ask(client, sales["dataset_id"], headers={"Fly-Client-IP": "1.1.1.1"}).status_code == 429
    assert ask(client, sales["dataset_id"], headers={"Fly-Client-IP": "2.2.2.2"}).status_code == 200

def test_upload_rate_limit(client, monkeypatch, upload_sales):
    monkeypatch.setitem(rate_limit.LIMITS, "upload", [(1, 60)])
    upload_sales()
    assert upload(client, "sales.csv", SALES_CSV, "text/csv").status_code == 429

@pytest.mark.parametrize("spec, rules", [
    ("20/minute", [(20, 60)]),
    ("20/minute, 200/day", [(20, 60), (200, 86400)]),
    ("", []),
    ("0", []),
])
def test_parse(spec, rules):
    assert rate_limit.parse(spec) == rules

@pytest.mark.parametrize("spec", ["20", "x/minute", "20/fortnight"])
def test_parse_rejects_bad_specs(spec):
    with pytest.raises(ValueError):
        rate_limit.parse(spec)

def test_store_windows(any_store):
    assert any_store.hit("k", 60) == (1, 60)
    count, reset = any_store.hit("k", 60)
    assert count == 2 and 0 < reset <= 60
    any_store.set("a", "b", 60)
    assert any_store.get("a") == "b" and any_store.get("missing") is None

def test_memory_store_is_bounded(monkeypatch):
    s = store.MemoryStore()
    monkeypatch.setattr(store.MemoryStore, "MAX_KEYS", 3)
    for i in range(5):
        s.set(str(i), "v", 60)
    assert len(s._data) == 3 and s.get("4") == "v" and s.get("0") is None

def test_ready_reports_cache(client):
    assert client.get("/ready").json()["cache"].startswith("disabled")

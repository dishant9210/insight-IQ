import pytest
from app.db import SessionLocal, QueryLog
from app.services import dataset_service

def ask(client, dataset_id, question="q"):
    return client.post("/api/query", json={"dataset_id": dataset_id, "question": question})

def test_answer_and_truncation(client, sales, fake_llm, monkeypatch):
    monkeypatch.setattr(dataset_service, "MAX_RESULT_ROWS", 3)
    fake_llm("```sql\nSELECT name, amount FROM data ORDER BY name;\n```")
    r = ask(client, sales["dataset_id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sql"] == "SELECT name, amount FROM data ORDER BY name"
    assert body["truncated"] is True and len(body["result"]) == 3
    assert body["result"][1]["amount"] is None
    assert body["insight"] == "insight text"

def test_sandbox_blocks_file_reads(client, sales, fake_llm):
    fake_llm("SELECT * FROM read_csv_auto('/etc/passwd')")
    r = ask(client, sales["dataset_id"])
    assert r.status_code == 400
    assert "Permission Error" in r.json()["detail"]

@pytest.mark.parametrize("sql", ["DROP TABLE data", "SELECT nope FROM data"])
def test_bad_sql_is_a_400(client, sales, fake_llm, sql):
    fake_llm(sql)
    assert ask(client, sales["dataset_id"]).status_code == 400

def test_empty_result_skips_the_insight_call(client, sales, fake_llm):
    fake_llm("SELECT * FROM data WHERE amount > 1000")
    body = ask(client, sales["dataset_id"]).json()
    assert body["result"] == [] and "No rows" in body["insight"]

def test_unknown_dataset(client, fake_llm):
    fake_llm("SELECT 1")
    assert ask(client, "nope").status_code == 404

def test_timeout(client, sales, fake_llm, monkeypatch):
    monkeypatch.setattr(dataset_service, "QUERY_TIMEOUT", 0.05)
    fake_llm("SELECT count(*) FROM range(300000000) a, range(100) b")
    assert ask(client, sales["dataset_id"]).status_code == 504

def test_every_query_is_logged(client, sales, fake_llm):
    fake_llm("SELECT count(*) AS n FROM data")
    ask(client, sales["dataset_id"], "how many rows")
    fake_llm("SELECT nope FROM data")
    ask(client, sales["dataset_id"], "broken one")

    with SessionLocal() as s:
        ok, bad = s.query(QueryLog).order_by(QueryLog.id).all()
    assert (ok.status, ok.question, ok.sql, ok.row_count) == ("ok", "how many rows", "SELECT count(*) AS n FROM data", 1)
    assert bad.status == "error" and bad.sql == "SELECT nope FROM data" and "nope" in bad.error
    assert ok.latency_ms >= 0

def test_missing_groq_key_is_a_clear_503(client, sales, monkeypatch):
    # the api must still start and accept uploads without a key; only questions need it
    from app.services import llm_service
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.setattr(llm_service, "sql_chain", None)
    monkeypatch.setattr(llm_service, "insight_chain", None)
    r = ask(client, sales["dataset_id"])
    assert r.status_code == 503 and "GROQ_API_KEY" in r.json()["detail"]

def test_prompt_names_the_table_explicitly(client, sales, fake_llm):
    # "Table data, 30 rows" read as prose made the model invent FROM orders
    chain = fake_llm("SELECT 1")
    ask(client, sales["dataset_id"])
    assert "Table name: data," in chain.inputs["schema"]

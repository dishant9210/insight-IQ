"""Retrieval: few-shot examples from past queries, feedback, the data
dictionary and schema selection. Runs on SQLite and, in CI, on Postgres
with pgvector — the two search paths must agree."""
import numpy as np
from app.services import retrieval, embeddings
from app.services.embeddings import HashEmbedder
from tests.conftest import upload, SALES_CSV

def ask(client, dataset_id, question):
    return client.post("/api/query", json={"dataset_id": dataset_id, "question": question})

def feedback(client, query_id, helpful):
    return client.post(f"/api/queries/{query_id}/feedback", json={"helpful": helpful})

SQL_A = "SELECT name, SUM(amount) AS total FROM data GROUP BY name"

def test_hash_embedder_shape_and_similarity():
    e = HashEmbedder()
    v = e.embed(["total amount by name", "what is the total amount by name", "count distinct dates"])
    assert v.shape == (3, embeddings.DIM)
    assert np.allclose(np.linalg.norm(v, axis=1), 1)
    assert np.allclose(e.embed(["total amount by name"])[0], v[0])   # deterministic
    assert v[0] @ v[1] >= e.min_similarity > v[0] @ v[2]

def test_similar_question_gets_past_answer_as_example(client, sales, fake_llm):
    fake_llm(SQL_A)
    first = ask(client, sales["dataset_id"], "total amount by name")
    assert first.json()["examples_used"] == 0

    chain = fake_llm("SELECT 1 AS n")
    second = ask(client, sales["dataset_id"], "what is the total amount by name")
    assert second.json()["examples_used"] == 1
    assert "Q: total amount by name" in chain.inputs["examples"]
    assert SQL_A in chain.inputs["examples"]

def test_unrelated_question_gets_no_examples(client, sales, fake_llm):
    fake_llm(SQL_A)
    ask(client, sales["dataset_id"], "total amount by name")
    chain = fake_llm("SELECT 1 AS n")
    assert ask(client, sales["dataset_id"], "count distinct dates").json()["examples_used"] == 0
    assert chain.inputs["examples"] == ""

def test_examples_carry_over_to_a_reupload_but_not_another_schema(client, sales, fake_llm, upload_sales):
    fake_llm(SQL_A)
    ask(client, sales["dataset_id"], "total amount by name")

    again = upload_sales()                     # same file, new dataset id
    fake_llm("SELECT 1 AS n")
    assert ask(client, again["dataset_id"], "what is the total amount by name").json()["examples_used"] == 1

    other = upload(client, "people.csv", "name,age\nann,3\n", "text/csv").json()
    assert ask(client, other["dataset_id"], "what is the total amount by name").json()["examples_used"] == 0

def test_failed_queries_are_not_examples(client, sales, fake_llm):
    fake_llm("SELECT nope FROM data")
    assert ask(client, sales["dataset_id"], "total amount by name").status_code == 400
    fake_llm("SELECT 1 AS n")
    assert ask(client, sales["dataset_id"], "what is the total amount by name").json()["examples_used"] == 0

def test_thumbs_down_removes_example_and_cached_answer(client, sales, fake_llm):
    fake_llm(SQL_A)
    qid = ask(client, sales["dataset_id"], "total amount by name").json()["query_id"]
    assert feedback(client, qid, False).json() == {"query_id": qid, "helpful": False}

    # the cached answer is gone: the model is asked again, without the bad SQL as a hint
    chain = fake_llm("SELECT 2 AS n")
    r = ask(client, sales["dataset_id"], "total amount by name").json()
    assert r["cached"] is False and r["sql"] == "SELECT 2 AS n"
    assert SQL_A not in chain.inputs["examples"]

def test_thumbs_down_on_any_copy_rules_the_sql_out(client, sales, fake_llm):
    fake_llm(SQL_A)
    ask(client, sales["dataset_id"], "total amount by name")
    cached_copy = ask(client, sales["dataset_id"], "total amount by name").json()
    assert cached_copy["cached"] is True
    feedback(client, cached_copy["query_id"], False)

    chain = fake_llm("SELECT 1 AS n")
    ask(client, sales["dataset_id"], "what is the total amount by name")
    assert SQL_A not in chain.inputs["examples"]

def test_feedback_validation(client, sales, fake_llm):
    assert feedback(client, 999999, True).status_code == 404
    fake_llm("SELECT nope FROM data")
    ask(client, sales["dataset_id"], "q")
    fake_llm(SQL_A)
    qid = ask(client, sales["dataset_id"], "total amount by name").json()["query_id"]
    assert feedback(client, qid, True).status_code == 200
    assert client.post(f"/api/queries/{qid}/feedback", json={}).status_code == 422

def test_retrieval_failure_still_answers(client, sales, fake_llm, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("model download failed")
    monkeypatch.setattr("app.api.query.embed_one", boom)
    fake_llm("SELECT 1 AS n")
    r = ask(client, sales["dataset_id"], "total amount by name")
    assert r.status_code == 200 and r.json()["examples_used"] == 0

# --- data dictionary -------------------------------------------------------

def put_notes(client, dataset_id, tables):
    return client.put(f"/api/datasets/{dataset_id}/dictionary", json={"tables": tables})

def test_dictionary_reaches_the_prompt(client, sales, fake_llm):
    r = put_notes(client, sales["dataset_id"], {"data": {"amount": "  revenue in INR,\nafter discount ", "name": ""}})
    assert r.status_code == 200
    assert r.json()["dictionary"] == {"data": {"amount": "revenue in INR, after discount"}}
    assert client.get(f"/api/datasets/{sales['dataset_id']}").json()["dictionary"] == r.json()["dictionary"]

    chain = fake_llm("SELECT 1 AS n")
    ask(client, sales["dataset_id"], "q")
    assert "amount (numeric) — revenue in INR, after discount" in chain.inputs["schema"]

def test_dictionary_change_misses_the_cache(client, sales, fake_llm):
    fake_llm("SELECT 1 AS n")
    ask(client, sales["dataset_id"], "q")
    assert ask(client, sales["dataset_id"], "q").json()["cached"] is True
    put_notes(client, sales["dataset_id"], {"data": {"amount": "in dollars"}})
    assert ask(client, sales["dataset_id"], "q").json()["cached"] is False

def test_dictionary_validation(client, sales):
    did = sales["dataset_id"]
    assert put_notes(client, did, {"nope": {"amount": "x"}}).status_code == 400
    assert put_notes(client, did, {"data": {"nope": "x"}}).status_code == 400
    assert put_notes(client, did, {"data": {"amount": "x" * 301}}).status_code == 400
    assert put_notes(client, "not-a-uuid", {}).status_code in (400, 404)

# --- schema selection ------------------------------------------------------

def _table(name, columns):
    return {"name": name, "sheet": None, "rows": 1, "columns": columns, "detected_types": {}, "preview": []}

def test_small_workbooks_send_every_table(client, sales, fake_llm):
    fake_llm("SELECT 1 AS n")
    assert ask(client, sales["dataset_id"], "q").json()["tables_used"] == ["data"]

def test_large_workbooks_send_the_closest_tables():
    tables = [_table(f"sheet_{i}", [f"col_{i}_a", f"col_{i}_b"]) for i in range(8)]
    tables[5] = _table("employee_salaries", ["employee", "salary", "department"])
    tables[2] = _table("departments", ["department", "manager"])
    vec = embeddings.embed_one("average salary per department")
    chosen = retrieval.select_tables(tables, vec, {}, limit=2)
    assert [t["name"] for t in chosen] == ["departments", "employee_salaries"]   # workbook order kept

def test_schema_hash_ignores_table_order_and_filename():
    a = [_table("orders", ["id", "amount"]), _table("customers", ["id", "city"])]
    assert retrieval.schema_hash(a) == retrieval.schema_hash(list(reversed(a)))
    assert retrieval.schema_hash(a) != retrieval.schema_hash([_table("orders", ["id", "total"])])

"""Question history, and keeping one account's questions out of another's prompts."""
from tests.conftest import SALES_CSV

SQL_A = "SELECT name, SUM(amount) AS total FROM data GROUP BY name"

def upload_as(c, headers=None):
    r = c.post("/api/upload", files={"file": ("sales.csv", SALES_CSV, "text/csv")}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["dataset_id"]

def ask(c, headers, dataset_id, question):
    return c.post("/api/query", json={"dataset_id": dataset_id, "question": question}, headers=headers)

def test_history_lists_my_questions_newest_first(alice, bob, fake_llm):
    a, h = alice
    d = upload_as(a, h)
    fake_llm(SQL_A, "alice spent the most")
    first = ask(a, h, d, "total amount by name").json()["query_id"]
    ask(a, h, d, "total amount by name")                       # cached copy
    fake_llm("SELECT nope FROM data")
    assert ask(a, h, d, "broken").status_code == 400

    items = a.get("/api/queries", headers=h).json()["items"]
    assert [i["question"] for i in items] == ["broken", "total amount by name", "total amount by name"]
    assert [i["status"] for i in items] == ["error", "ok", "ok"]
    assert [i["cached"] for i in items] == [False, True, False]
    assert items[0]["error"] and items[1]["filename"] == "sales.csv"
    assert items[2]["query_id"] == first

    b, bh = bob
    assert b.get("/api/queries", headers=bh).json()["items"] == []

def test_history_pages(alice, fake_llm):
    a, h = alice
    d = upload_as(a, h)
    fake_llm("SELECT 1 AS n")
    for i in range(5):
        ask(a, h, d, f"question {i}")
    page = a.get("/api/queries?limit=2", headers=h).json()
    seen = [i["question"] for i in page["items"]]
    while page["next_before"]:
        page = a.get(f"/api/queries?limit=2&before={page['next_before']}", headers=h).json()
        seen += [i["question"] for i in page["items"]]
    assert seen == [f"question {i}" for i in reversed(range(5))]

def test_history_filters_by_dataset(alice, fake_llm):
    a, h = alice
    d1, d2 = upload_as(a, h), upload_as(a, h)
    fake_llm("SELECT 1 AS n")
    ask(a, h, d1, "one")
    ask(a, h, d2, "two")
    items = a.get(f"/api/queries?dataset_id={d2}", headers=h).json()["items"]
    assert [i["question"] for i in items] == ["two"]

def test_history_needs_sign_in(client):
    assert client.get("/api/queries").status_code == 401
    assert client.get("/api/queries/1").status_code == 401

def test_past_answer_reruns_without_the_model(alice, bob, fake_llm):
    a, h = alice
    d = upload_as(a, h)
    fake_llm(SQL_A, "alice spent the most")
    qid = ask(a, h, d, "total amount by name").json()["query_id"]

    chain = fake_llm("SELECT 'should not run' AS x")
    r = a.get(f"/api/queries/{qid}", headers=h).json()
    assert chain.inputs is None                                  # no model call
    assert r["dataset_available"] is True and r["sql"] == SQL_A
    assert r["insight"] == "alice spent the most"
    assert {"name": "carol", "total": 30} in r["result"]

    b, bh = bob
    assert b.get(f"/api/queries/{qid}", headers=bh).status_code == 404

def test_past_answer_after_the_dataset_is_gone(alice, fake_llm):
    a, h = alice
    d = upload_as(a, h)
    fake_llm(SQL_A, "alice spent the most")
    qid = ask(a, h, d, "total amount by name").json()["query_id"]
    assert a.delete(f"/api/datasets/{d}", headers=h).status_code == 204

    r = a.get(f"/api/queries/{qid}", headers=h).json()
    assert r["dataset_available"] is False and r["result"] == []
    assert r["sql"] == SQL_A and r["insight"] == "alice spent the most"
    assert a.get("/api/queries", headers=h).json()["items"][0]["filename"] is None

def test_failed_question_has_no_answer_to_show(alice, fake_llm):
    a, h = alice
    d = upload_as(a, h)
    fake_llm("SELECT nope FROM data")
    ask(a, h, d, "broken")
    qid = a.get("/api/queries", headers=h).json()["items"][0]["query_id"]
    assert a.get(f"/api/queries/{qid}", headers=h).status_code == 409

def test_feedback_only_on_your_own_questions(client, alice, bob, fake_llm):
    a, h = alice
    d = upload_as(a, h)
    fake_llm("SELECT 1 AS n")
    qid = ask(a, h, d, "q").json()["query_id"]
    b, bh = bob
    for c, headers in ((b, bh), (client, None)):
        assert c.post(f"/api/queries/{qid}/feedback", json={"helpful": False}, headers=headers).status_code == 404
    assert a.post(f"/api/queries/{qid}/feedback", json={"helpful": True}, headers=h).status_code == 200

def test_accounts_dont_share_examples(client, alice, bob, fake_llm):
    a, h = alice
    b, bh = bob
    fake_llm(SQL_A)
    ask(a, h, upload_as(a, h), "total amount by name")

    fake_llm("SELECT 1 AS n")
    # same schema, similar question, different account: nothing from alice
    assert ask(b, bh, upload_as(b, bh), "what is the total amount by name").json()["examples_used"] == 0
    assert ask(client, None, upload_as(client), "what is the total amount by name").json()["examples_used"] == 0
    # alice still learns from herself (and from the guest pool)
    chain = fake_llm("SELECT 1 AS n")
    assert ask(a, h, upload_as(a, h), "what is the total amount by name").json()["examples_used"] >= 1
    assert SQL_A in chain.inputs["examples"]

def test_guest_answers_help_everyone(client, alice, fake_llm):
    fake_llm(SQL_A)
    ask(client, None, upload_as(client), "total amount by name")
    a, h = alice
    fake_llm("SELECT 1 AS n")
    assert ask(a, h, upload_as(a, h), "what is the total amount by name").json()["examples_used"] == 1

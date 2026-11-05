"""The eval harness, without the model: the scorer, the case file, and that
every gold query actually runs. Keeps cases.yaml honest in normal CI; the
model-in-the-loop run is the separate eval workflow."""
import asyncio
from datetime import date, datetime
import pytest
from app.services import llm_service
from app.services.dataset_service import execute_query, tables_of
from evals import harness, run
from evals.scoring import match, norm
from tests.conftest import FakeChain

DATASETS, CASES = run.load_cases(run.os.path.join(run.HERE, "cases.yaml"))

# --- scorer ----------------------------------------------------------------

GOLD = [{"region": "North", "total": 10.0}, {"region": "South", "total": 20.0}]

def test_names_order_and_extra_columns_dont_matter():
    pred = [{"n": 2, "s": 20.004, "r": "South"}, {"n": 1, "s": 10, "r": "North"}]
    assert match(GOLD, pred)

def test_values_must_match():
    assert not match(GOLD, [{"r": "North", "t": 10.0}, {"r": "South", "t": 21.0}])
    # right values, wrongly paired across rows
    assert not match(GOLD, [{"r": "North", "t": 20.0}, {"r": "South", "t": 10.0}])

def test_row_count_must_match():
    assert not match(GOLD, GOLD[:1])
    assert not match(GOLD[:1], GOLD)

def test_order_only_when_asked():
    flipped = list(reversed(GOLD))
    assert match(GOLD, flipped)
    assert not match(GOLD, flipped, ordered=True)
    assert match(GOLD, GOLD, ordered=True)

def test_missing_column_fails():
    assert not match(GOLD, [{"region": "North"}, {"region": "South"}])

def test_columns_with_identical_values_are_assigned_consistently():
    gold = [{"a": 1, "b": 2}, {"a": 2, "b": 1}]
    assert match(gold, [{"x": 2, "y": 1}, {"x": 1, "y": 2}])          # same rows, other order
    assert not match(gold, [{"x": 1, "y": 1}, {"x": 2, "y": 2}])

def test_empty_results():
    assert match([], [])
    assert not match([], [{"a": 1}])

@pytest.mark.parametrize("value, expected", [
    (3, 3.0), (2.999, 3.0), (-0.0, 0.0), (float("nan"), None), (None, None),
    (datetime(2024, 1, 1), "2024-01-01"), (date(2024, 1, 1), "2024-01-01"),
    ("2024-01-01T00:00:00.000", "2024-01-01"), ("2024-01-01T10:30:00", "2024-01-01T10:30:00"),
    (" North ", "North"), (True, True),
])
def test_norm(value, expected):
    assert norm(value) == expected

# --- case file -------------------------------------------------------------

def test_case_ids_are_unique_and_datasets_exist():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
    assert all(c["dataset"] in DATASETS for c in CASES)
    assert len(CASES) >= 20

@pytest.fixture
def loaded():
    out = {}
    for name, spec in DATASETS.items():
        meta = harness.load(spec["file"])
        out[name] = {"id": meta["dataset_id"], "tables": tables_of(meta), "notes": spec.get("notes")}
    return out

def test_notes_name_real_columns(loaded):
    for name, ds in loaded.items():
        columns = {t["name"]: set(t["columns"]) for t in ds["tables"]}
        for table, cols in (ds["notes"] or {}).items():
            assert set(cols) <= columns[table], f"{name}.{table}: unknown columns in notes"

def test_every_gold_query_runs_and_returns_rows(loaded):
    for c in CASES:
        for g in c["gold"]:
            rows, truncated = execute_query(loaded[c["dataset"]]["id"], g)
            assert rows and not truncated, c["id"]
            assert match(rows, rows, c["ordered"]), c["id"]

def _top_two_differ(dataset_id: str, gold: str) -> bool:
    """Select the ORDER BY expression next to the answer and check #1 beats #2."""
    order = gold.split("ORDER BY", 1)[1].rsplit("LIMIT", 1)[0].strip()
    key = order[:-4].strip() if order.upper().endswith(" DESC") else order
    probe = gold.replace("SELECT ", f"SELECT {key} AS _k, ", 1).replace("LIMIT 1", "LIMIT 2")
    rows, _ = execute_query(dataset_id, probe)
    return len(rows) < 2 or rows[0]["_k"] != rows[1]["_k"]

def test_single_answer_ranking_cases_have_no_tie(loaded):
    # "which X has the most Y" with a tie has two right answers, and the gold only knows one
    for c in CASES:
        g = c["gold"][0]
        if "ranking" in c["tags"] and "LIMIT 1" in g:
            assert _top_two_differ(loaded[c["dataset"]]["id"], g), c["id"]

def test_tie_check_catches_a_tie(loaded):
    tied = "SELECT agt FROM data WHERE st = 'R' GROUP BY agt ORDER BY COUNT(*) DESC LIMIT 1"
    assert not _top_two_differ(loaded["tickets"]["id"], tied)

# --- runner, with the model stubbed out ------------------------------------

def _run(case, ds, monkeypatch, sql):
    monkeypatch.setattr(llm_service, "sql_chain", FakeChain(sql))
    monkeypatch.setattr(llm_service, "insight_chain", FakeChain(""))
    gold_rows = [execute_query(ds["id"], g)[0] for g in case["gold"]]
    return asyncio.run(run.run_case(case, ds, gold_rows))

def test_runner_scores_outcomes(loaded, monkeypatch):
    case = next(c for c in CASES if c["id"] == "store-qty-by-category")
    ds = loaded["store"]
    assert _run(case, ds, monkeypatch, case["gold"][0])["outcome"] == "pass"
    assert _run(case, ds, monkeypatch, "SELECT 1")["outcome"] == "wrong"
    assert _run(case, ds, monkeypatch, "DROP TABLE orders")["outcome"] == "invalid"
    assert _run(case, ds, monkeypatch, "SELECT nope FROM orders")["outcome"] == "exec_error"

def test_any_gold_alternative_passes(loaded, monkeypatch):
    case = next(c for c in CASES if c["id"] == "sales-orders-per-month")
    for g in case["gold"]:
        assert _run(case, loaded["sales"], monkeypatch, g)["outcome"] == "pass"

def test_summary_and_markdown():
    results = [
        {"id": "a", "tags": ["join"], "outcome": "pass", "sql": "SELECT 1", "error": None, "latency_ms": 10},
        {"id": "b", "tags": ["join", "notes"], "outcome": "wrong", "sql": "SELECT a | b", "error": None, "latency_ms": 30},
    ]
    s = run.summarise(results, "m", True)
    assert s["accuracy"] == 0.5 and s["by_tag"]["join"] == {"passed": 1, "total": 2, "accuracy": 0.5}
    md = run.markdown(s, results, 0.8)
    assert "❌ 1/2" in md and "`b`" in md and "a \\| b" in md

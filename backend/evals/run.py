"""Text-to-SQL eval: ask the real model every question in cases.yaml, run its
SQL and the gold SQL on the same data, and score by execution match.

    python -m evals.run                      # all cases, fails below EVAL_MIN_ACCURACY
    python -m evals.run --only notes         # cases with that tag or id
    python -m evals.run --no-notes           # ablation: hide the column notes
    python -m evals.run --report out.json    # machine-readable results

Needs GROQ_API_KEY. Retrieval is off — each question is scored on the prompt
alone, so a regression in the prompt or the model can't hide behind examples.
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict

from evals import harness

HERE = os.path.dirname(__file__)

def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cases", default=os.path.join(HERE, "cases.yaml"))
    p.add_argument("--only", help="run only cases whose id or a tag matches")
    p.add_argument("--no-notes", action="store_true", help="don't show the model the column notes")
    p.add_argument("--min-accuracy", type=float, default=float(os.getenv("EVAL_MIN_ACCURACY", "0.8")))
    p.add_argument("--report", help="write full results as JSON here")
    p.add_argument("--summary", default=os.getenv("GITHUB_STEP_SUMMARY"), help="append a markdown summary here")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between questions (rate limits)")
    return p.parse_args(argv)

def load_cases(path: str, only: str | None = None) -> tuple[dict, list[dict]]:
    import yaml
    with open(path) as f:
        spec = yaml.safe_load(f)
    cases = spec["cases"]
    if only:
        cases = [c for c in cases if c["id"] == only or only in c.get("tags", [])]
    for c in cases:
        c["gold"] = c["gold"] if isinstance(c["gold"], list) else [c["gold"]]
        c.setdefault("ordered", False)
        c.setdefault("tags", [])
    return spec["datasets"], cases

async def _generate(question, tables, notes, retries=3):
    from fastapi import HTTPException
    from app.services.llm_service import generate_sql
    for attempt in range(retries + 1):
        try:
            return await generate_sql(question, tables, notes, examples=[])
        except HTTPException as e:
            if e.status_code == 429 and attempt < retries:
                await asyncio.sleep(10 * (attempt + 1))
                continue
            raise

async def run_case(case: dict, dataset: dict, gold_rows: list[list[dict]]) -> dict:
    import duckdb
    from fastapi import HTTPException
    from app.services.dataset_service import execute_query

    result = {"id": case["id"], "tags": case["tags"], "question": case["question"], "sql": None, "error": None}
    started = time.perf_counter()
    try:
        sql = await _generate(case["question"], dataset["tables"], dataset["notes"])
        result["sql"] = sql
        rows, _ = await asyncio.to_thread(execute_query, dataset["id"], sql)
        from evals.scoring import match
        ok = any(match(g, rows, case["ordered"]) for g in gold_rows)
        result["outcome"] = "pass" if ok else "wrong"
        if not ok:
            result["got"] = rows[:5]
    except HTTPException as e:
        result["sql"] = getattr(e, "sql", None)
        # 400 from the guard = the model wrote something that isn't one SELECT
        result["outcome"] = "invalid" if e.status_code == 400 else "llm_error"
        result["error"] = str(e.detail)
    except duckdb.Error as e:
        result["outcome"] = "exec_error"
        result["error"] = str(e).splitlines()[0]
    result["latency_ms"] = int((time.perf_counter() - started) * 1000)
    return result

def summarise(results: list[dict], model: str, notes: bool) -> dict:
    passed = sum(r["outcome"] == "pass" for r in results)
    by_tag = defaultdict(lambda: [0, 0])
    for r in results:
        for t in r["tags"]:
            by_tag[t][0] += r["outcome"] == "pass"
            by_tag[t][1] += 1
    outcomes = defaultdict(int)
    for r in results:
        outcomes[r["outcome"]] += 1
    latencies = sorted(r["latency_ms"] for r in results)
    return {
        "model": model,
        "column_notes": notes,
        "cases": len(results),
        "passed": passed,
        "accuracy": round(passed / len(results), 4) if results else 0.0,
        "outcomes": dict(outcomes),
        "by_tag": {t: {"passed": p, "total": n, "accuracy": round(p / n, 4)} for t, (p, n) in sorted(by_tag.items())},
        "latency_ms_p50": latencies[len(latencies) // 2] if latencies else 0,
        "latency_ms_max": latencies[-1] if latencies else 0,
    }

def markdown(summary: dict, results: list[dict], min_accuracy: float) -> str:
    verdict = "✅" if summary["accuracy"] >= min_accuracy else "❌"
    lines = [
        f"## Text-to-SQL eval {verdict} {summary['passed']}/{summary['cases']} "
        f"({summary['accuracy']:.0%}, gate {min_accuracy:.0%})",
        "",
        f"Model `{summary['model']}` · column notes {'on' if summary['column_notes'] else 'off'} · "
        f"p50 {summary['latency_ms_p50']} ms",
        "",
        "| tag | passed | accuracy |",
        "| :-- | --: | --: |",
    ]
    lines += [f"| {t} | {v['passed']}/{v['total']} | {v['accuracy']:.0%} |" for t, v in summary["by_tag"].items()]
    failed = [r for r in results if r["outcome"] != "pass"]
    if failed:
        lines += ["", "| failed case | outcome | model SQL |", "| :-- | :-- | :-- |"]
        for r in failed:
            sql = " ".join((r["sql"] or r["error"] or "").split()).replace("|", "\\|")
            lines.append(f"| `{r['id']}` | {r['outcome']} | `{sql[:160]}` |")
    return "\n".join(lines) + "\n"

async def main(argv=None) -> int:
    args = parse_args(argv)
    harness.isolate()
    from dotenv import load_dotenv
    load_dotenv()
    if not os.getenv("GROQ_API_KEY"):
        print("GROQ_API_KEY is not set — the eval needs the real model.", file=sys.stderr)
        return 2

    from app.services.dataset_service import execute_query, tables_of

    datasets_spec, cases = load_cases(args.cases, args.only)
    if not cases:
        print(f"No cases match {args.only!r}", file=sys.stderr)
        return 2

    datasets = {}
    for name in {c["dataset"] for c in cases}:
        meta = harness.load(datasets_spec[name]["file"])
        datasets[name] = {
            "id": meta["dataset_id"],
            "tables": tables_of(meta),
            "notes": None if args.no_notes else datasets_spec[name].get("notes"),
        }

    results = []
    for i, case in enumerate(cases):
        ds = datasets[case["dataset"]]
        gold_rows = [execute_query(ds["id"], g)[0] for g in case["gold"]]
        r = await run_case(case, ds, gold_rows)
        results.append(r)
        mark = "PASS" if r["outcome"] == "pass" else r["outcome"].upper()
        print(f"[{i + 1:>2}/{len(cases)}] {mark:<10} {case['id']}  ({r['latency_ms']} ms)", flush=True)
        if r["outcome"] != "pass":
            print(f"             sql: {' '.join((r['sql'] or '').split())[:200]}")
            if r.get("error"):
                print(f"             error: {r['error']}")
        if args.delay and i < len(cases) - 1:
            await asyncio.sleep(args.delay)

    summary = summarise(results, os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), not args.no_notes)
    md = markdown(summary, results, args.min_accuracy)
    print()
    print(md)
    if args.summary:
        with open(args.summary, "a") as f:
            f.write(md)
    if args.report:
        with open(args.report, "w") as f:
            json.dump({"summary": summary, "results": results}, f, indent=2, default=str)

    return 0 if summary["accuracy"] >= args.min_accuracy else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

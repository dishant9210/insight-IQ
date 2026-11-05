import os, asyncio, time
import duckdb
import groq
from fastapi import HTTPException
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from app.services.sql_guard import clean_sql, validate_sql
from app.services.dataset_service import execute_query
from app import metrics
from app.tracing import tracer

load_dotenv()


SQL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a SQL expert. Given a dataset schema and a question,
write a single DuckDB SQL query against the tables below.

Rules:
- Return ONLY the SQL query, no explanation, no markdown fences
- Only SELECT statements — no INSERT, UPDATE, DELETE, DROP
- Table and column names must match the schema exactly; query only the tables
  listed below (a single-table dataset is always the table named data)
- If the answer needs columns from more than one table, JOIN them on a shared key
- Use DuckDB syntax (e.g. STRFTIME for dates)
- Column notes after a dash come from the dataset owner; trust them over guesses

{schema}
{examples}"""),
    ("human", "{question}")
])

INSIGHT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a data analyst. Given SQL results, write a 2-sentence insight. Be specific with numbers."),
    ("human", "Question: {question}\nResults: {results}")
])

def _schema_str(tables: list[dict], dictionary: dict | None = None) -> str:
    parts = []
    for t in tables:
        dtypes = t["detected_types"]
        notes = (dictionary or {}).get(t["name"], {})
        cols = "\n".join(
            f"  {col} ({dtypes.get(col, 'unknown')})" + (f" — {notes[col]}" if notes.get(col) else "")
            for col in t["columns"]
        )
        label = f" (sheet '{t['sheet']}')" if t.get("sheet") else ""
        parts.append(
            f"Table name: {t['name']}{label}, {t['rows']} rows\n"
            f"Columns:\n{cols}\n"
            f"Sample rows: {t['preview'][:3]}"
        )
    return "\n\n".join(parts)

def _examples_str(examples: list[dict]) -> str:
    if not examples:
        return ""
    shots = "\n\n".join(f"Q: {e['question']}\nSQL: {e['sql']}" for e in examples)
    return (
        "\nSimilar questions already answered on this same schema. Reuse their "
        "patterns where they fit, but answer the new question:\n\n" + shots + "\n"
    )

# Built on first use, so the api (and /health, /ready, uploads) still starts
# without a Groq key — only answering questions needs one.
sql_chain = None
insight_chain = None

def _chains():
    global sql_chain, insight_chain
    if sql_chain is None or insight_chain is None:
        if not os.getenv("GROQ_API_KEY"):
            raise HTTPException(503, "GROQ_API_KEY is not set on the server, so questions can't be answered yet.")
        # temperature 0 — we want the same question to produce the same SQL
        llm = ChatGroq(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), temperature=0)
        # no output parser: _ask reads the text and the token usage off the message
        sql_chain = SQL_PROMPT | llm
        insight_chain = INSIGHT_PROMPT | llm
    return sql_chain, insight_chain

def _fail(status: int, detail: str, sql: str) -> HTTPException:
    # keep the SQL on the error so the query log can record what the model wrote
    e = HTTPException(status, detail)
    e.sql = sql
    return e

async def _ask(chain, inputs: dict, step: str) -> str:
    """One model call, timed and traced, with its token usage counted."""
    started = time.perf_counter()
    with tracer.start_as_current_span(f"llm.{step}") as span:
        outcome = "error"
        try:
            msg = await chain.ainvoke(inputs)
            outcome = "ok"
        except groq.AuthenticationError:
            raise HTTPException(502, "Language model rejected the API key. Check GROQ_API_KEY.")
        except groq.RateLimitError:
            outcome = "rate_limited"
            raise HTTPException(429, "Language model rate limit hit. Try again in a moment.")
        except groq.APIError as e:
            raise HTTPException(502, f"Language model request failed: {e.__class__.__name__}")
        finally:
            span.set_attribute("llm.outcome", outcome)
            metrics.LLM_LATENCY.labels(step, outcome).observe(time.perf_counter() - started)

        usage = getattr(msg, "usage_metadata", None) or {}
        for kind in ("input_tokens", "output_tokens"):
            if usage.get(kind):
                metrics.LLM_TOKENS.labels(step, kind.split("_")[0]).inc(usage[kind])
                span.set_attribute(f"llm.{kind}", usage[kind])
    return msg.content if hasattr(msg, "content") else msg

async def generate_sql(
    question: str,
    tables: list[dict],
    dictionary: dict | None = None,
    examples: list[dict] | None = None,
) -> str:
    """Question → cleaned, validated SQL. Shared by the api and the eval runner."""
    sql_chain, _ = _chains()
    raw_sql = await _ask(sql_chain, {
        "schema": _schema_str(tables, dictionary),
        "examples": _examples_str(examples or []),
        "question": question
    }, step="sql")
    sql = clean_sql(raw_sql)
    try:
        validate_sql(sql)
    except ValueError as e:
        raise _fail(400, str(e), sql)
    return sql

async def answer_question(
    question: str,
    dataset_id: str,
    tables: list[dict],
    dictionary: dict | None = None,
    examples: list[dict] | None = None,
) -> dict:
    # Steps 1–2: generate and validate SQL
    sql = await generate_sql(question, tables, dictionary, examples)
    _, insight_chain = _chains()

    # Step 3: Execute (off the event loop — DuckDB is synchronous)
    try:
        with tracer.start_as_current_span("sql.execute"), metrics.Timer() as t:
            results, truncated = await asyncio.to_thread(execute_query, dataset_id, sql)
        metrics.SQL_LATENCY.observe(t.seconds)
    except duckdb.InterruptException:
        raise _fail(504, "Query timed out", sql)
    except duckdb.Error as e:
        # first line only — DuckDB appends a multi-line caret pointer
        raise _fail(400, f"Query failed: {str(e).splitlines()[0]}", sql)

    # Step 4: Generate insight
    if results:
        insight = await _ask(insight_chain, {
            "question": question,
            "results": str(results[:10])
        }, step="insight")
    else:
        insight = "No rows matched this question."

    # Step 5: Suggest chart type
    chart_type = _suggest_chart(sql, results)

    return {
        "sql": sql,
        "result": results,
        "insight": insight,
        "chart_type": chart_type,
        "truncated": truncated,
    }

def _suggest_chart(sql: str, results: list[dict]) -> str:
    """Simple heuristic — upgrade with LLM in Week 2."""
    if not results:
        return "table"
    keys = list(results[0].keys())
    sql_lower = sql.lower()
    if "group by" in sql_lower and len(keys) == 2:
        return "bar"
    if any(w in sql_lower for w in ["month", "year", "date", "time"]):
        return "line"
    return "table"

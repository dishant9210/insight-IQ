import os, asyncio
import duckdb
import groq
from fastapi import HTTPException
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.services.sql_guard import clean_sql, validate_sql
from app.services.dataset_service import execute_query

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
        sql_chain = SQL_PROMPT | llm | StrOutputParser()
        insight_chain = INSIGHT_PROMPT | llm | StrOutputParser()
    return sql_chain, insight_chain

def _fail(status: int, detail: str, sql: str) -> HTTPException:
    # keep the SQL on the error so the query log can record what the model wrote
    e = HTTPException(status, detail)
    e.sql = sql
    return e

async def _ask(chain, inputs: dict) -> str:
    try:
        return await chain.ainvoke(inputs)
    except groq.AuthenticationError:
        raise HTTPException(502, "Language model rejected the API key. Check GROQ_API_KEY.")
    except groq.RateLimitError:
        raise HTTPException(429, "Language model rate limit hit. Try again in a moment.")
    except groq.APIError as e:
        raise HTTPException(502, f"Language model request failed: {e.__class__.__name__}")

async def answer_question(
    question: str,
    dataset_id: str,
    tables: list[dict],
    dictionary: dict | None = None,
    examples: list[dict] | None = None,
) -> dict:
    schema = _schema_str(tables, dictionary)

    # Step 1: Generate SQL
    sql_chain, insight_chain = _chains()
    raw_sql = await _ask(sql_chain, {
        "schema": schema,
        "examples": _examples_str(examples or []),
        "question": question
    })

    # Step 2: Validate
    sql = clean_sql(raw_sql)
    try:
        validate_sql(sql)
    except ValueError as e:
        raise _fail(400, str(e), sql)

    # Step 3: Execute (off the event loop — DuckDB is synchronous)
    try:
        results, truncated = await asyncio.to_thread(execute_query, dataset_id, sql)
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
        })
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

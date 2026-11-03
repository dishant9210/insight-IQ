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

# temperature 0 — we want the same question to produce the same SQL
llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    temperature=0,
)

SQL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a SQL expert. Given a dataset schema and a question,
write a single DuckDB SQL query on a table called 'data'.

Rules:
- Return ONLY the SQL query, no explanation, no markdown fences
- Only SELECT statements — no INSERT, UPDATE, DELETE, DROP
- Column names must match the schema exactly
- Use DuckDB syntax (e.g. STRFTIME for dates)

Schema:
{schema}

Sample rows:
{sample}
"""),
    ("human", "{question}")
])

INSIGHT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a data analyst. Given SQL results, write a 2-sentence insight. Be specific with numbers."),
    ("human", "Question: {question}\nResults: {results}")
])

def _schema_str(columns: list[str], dtypes: dict) -> str:
    cols = "\n".join(f"  {col} ({dtypes.get(col, 'unknown')})" for col in columns)
    return f"Columns:\n{cols}"

sql_chain = SQL_PROMPT | llm | StrOutputParser()
insight_chain = INSIGHT_PROMPT | llm | StrOutputParser()

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
    columns: list[str],
    dtypes: dict,
    sample: list[dict]
) -> dict:
    schema = _schema_str(columns, dtypes)

    # Step 1: Generate SQL
    raw_sql = await _ask(sql_chain, {
        "schema": schema,
        "sample": str(sample[:3]),
        "question": question
    })

    # Step 2: Validate
    sql = clean_sql(raw_sql)
    try:
        validate_sql(sql)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Step 3: Execute (off the event loop — DuckDB is synchronous)
    try:
        results, truncated = await asyncio.to_thread(execute_query, dataset_id, sql)
    except duckdb.InterruptException:
        raise HTTPException(504, "Query timed out")
    except duckdb.Error as e:
        # first line only — DuckDB appends a multi-line caret pointer
        raise HTTPException(400, f"Query failed: {str(e).splitlines()[0]}")

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

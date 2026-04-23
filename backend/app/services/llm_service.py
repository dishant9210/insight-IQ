from langchain_groq import ChatGroq

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.services.dataset_service import execute_query
import os, re
from dotenv import load_dotenv

load_dotenv()

# Use Groq (free) — just change base_url
# llm = ChatGroq(
#     model="llama-3.3-70b-versatile",
#     openai_api_key=os.getenv("GROQ_API_KEY"),
#     openai_api_base="https://api.groq.com/openai/v1",
#     # temperature=0,  # deterministic — we want consistent SQL
# )

llm = ChatGroq(
    model_name="llama-3.3-70b-versatile",
    temperature=0.7
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

def _validate_sql(sql: str) -> str:
    """Safety check — only allow SELECT statements."""
    sql = sql.strip().rstrip(';')
    forbidden = ['insert', 'update', 'delete', 'drop', 'create', 'alter', 'truncate']
    sql_lower = sql.lower()
    for word in forbidden:
        if re.search(r'\b' + word + r'\b', sql_lower):
            raise ValueError(f"Forbidden SQL keyword: {word}")
    if not sql_lower.lstrip().startswith('select'):
        raise ValueError("Only SELECT queries allowed")
    return sql

def _schema_str(columns: list[str], dtypes: dict, sample: list[dict]) -> str:
    cols = "\n".join(f"  {col} ({dtypes.get(col, 'unknown')})" for col in columns)
    return f"Columns:\n{cols}"

sql_chain = SQL_PROMPT | llm | StrOutputParser()
insight_chain = INSIGHT_PROMPT | llm | StrOutputParser()

async def answer_question(
    question: str,
    dataset_id: str,
    columns: list[str],
    dtypes: dict,
    sample: list[dict]
) -> dict:
    schema = _schema_str(columns, dtypes, sample)
    
    # Step 1: Generate SQL
    raw_sql = await sql_chain.ainvoke({
        "schema": schema,
        "sample": str(sample[:3]),
        "question": question
    })
    
    # Step 2: Validate
    sql = _validate_sql(raw_sql)
    
    # Step 3: Execute
    results = execute_query(dataset_id, sql)
    
    # Step 4: Generate insight
    insight = await insight_chain.ainvoke({
        "question": question,
        "results": str(results[:10])
    })
    
    # Step 5: Suggest chart type
    chart_type = _suggest_chart(sql, results)
    
    return {"sql": sql, "result": results, "insight": insight, "chart_type": chart_type}

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
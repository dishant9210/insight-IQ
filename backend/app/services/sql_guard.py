import re
import duckdb

# Belt-and-braces keyword check. The real guard is the parser check below
# plus the read-only, no-external-access connection in dataset_service.
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|truncate|copy|export|attach|install|load|pragma)\b",
    re.IGNORECASE,
)

def clean_sql(raw: str) -> str:
    """Strip markdown fences and trailing semicolons the model sometimes adds."""
    sql = raw.strip()
    sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s*```$", "", sql)
    return sql.strip().rstrip(";").strip()

def validate_sql(sql: str) -> str:
    """Allow exactly one SELECT statement. Raises ValueError otherwise."""
    if not sql:
        raise ValueError("Model returned an empty query")

    # The model sometimes answers in prose ("I can't help with that") instead of SQL.
    if not re.match(r"\s*(select|with)\b", sql, re.IGNORECASE):
        raise ValueError("The model did not return a SQL query for that question. Try rephrasing it.")

    if FORBIDDEN.search(sql):
        raise ValueError("Only read-only SELECT queries are allowed")

    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as e:
        raise ValueError(f"Could not parse SQL: {e}")

    if len(statements) != 1:
        raise ValueError("Exactly one statement is allowed")

    if statements[0].type != duckdb.StatementType.SELECT:
        raise ValueError("Only SELECT statements are allowed")

    return sql

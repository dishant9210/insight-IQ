import pytest
from app.services.sql_guard import clean_sql, validate_sql

def test_strips_fences_and_semicolons():
    assert clean_sql("```sql\nSELECT 1;\n```") == "SELECT 1"
    assert clean_sql("  SELECT 1 ;; ") == "SELECT 1"

@pytest.mark.parametrize("sql", [
    "DROP TABLE data",
    "SELECT 1; SELECT 2",
    "COPY data TO 'x.csv'",
    "INSERT INTO data VALUES (1)",
    "PRAGMA database_list",
    "",
    "SELEC nope",
])
def test_rejects_non_select(sql):
    with pytest.raises(ValueError):
        validate_sql(sql)

def test_allows_cte():
    validate_sql("WITH t AS (SELECT 1 AS x) SELECT * FROM t")

def test_file_reads_pass_the_guard():
    # syntactically a SELECT — it has to be stopped by the sandbox at execution (see test_query)
    validate_sql("SELECT * FROM read_csv_auto('/etc/passwd')")

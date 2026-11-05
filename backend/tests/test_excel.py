import io
import pandas as pd
from app.services.loaders.excel_loader import _table_name
from tests.conftest import upload

def workbook(**sheets) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name.replace("_", " "), index=False)
    return buf.getvalue()

def test_table_names():
    taken = {"data"}
    names = [_table_name(s, taken) for s in ["Orders", "Customer List", "2024", "Order", "orders", "Data", "  "]]
    assert names == ["orders", "customer_list", "sheet_2024", "order_sheet", "orders_2", "data_2", "sheet"]

BOOK = workbook(
    Orders=pd.DataFrame({"Order ID": [1, 2, 3], "Customer ID": [10, 20, 10], "Amount": [100, 250, 50]}),
    Customer_List=pd.DataFrame({"Customer ID": [10, 20], "City": ["Delhi", "Pune"]}),
    Notes=pd.DataFrame(),
)

def test_every_sheet_becomes_a_table(client):
    body = upload(client, "book.xlsx", BOOK).json()
    assert [t["name"] for t in body["tables"]] == ["orders", "customer_list"]
    assert body["tables"][1]["sheet"] == "Customer List"
    assert any("Notes" in w for w in body["warnings"])
    assert body["columns"] == ["order_id", "customer_id", "amount"]

def test_join_across_sheets(client, fake_llm):
    did = upload(client, "book.xlsx", BOOK).json()["dataset_id"]
    chain = fake_llm(
        "SELECT c.city, SUM(o.amount) AS total FROM orders o "
        "JOIN customer_list c ON o.customer_id = c.customer_id GROUP BY c.city ORDER BY total DESC"
    )
    r = client.post("/api/query", json={"dataset_id": did, "question": "revenue by city"})
    assert r.status_code == 200, r.text
    assert r.json()["result"] == [{"city": "Pune", "total": 250}, {"city": "Delhi", "total": 150}]
    assert "Table name: orders" in chain.inputs["schema"]
    assert "Table name: customer_list (sheet 'Customer List')" in chain.inputs["schema"]

def test_data_alias_points_at_first_sheet(client, fake_llm):
    did = upload(client, "book.xlsx", BOOK).json()["dataset_id"]
    fake_llm("SELECT count(*) AS n FROM data")
    r = client.post("/api/query", json={"dataset_id": did, "question": "q"})
    assert r.json()["result"] == [{"n": 3}]

def test_duplicate_join_columns_are_renamed(client, fake_llm):
    did = upload(client, "book.xlsx", BOOK).json()["dataset_id"]
    fake_llm("SELECT * FROM orders o JOIN customer_list c ON o.customer_id = c.customer_id")
    r = client.post("/api/query", json={"dataset_id": did, "question": "q"})
    assert r.status_code == 200 and "customer_id_1" in r.json()["result"][0]

def test_all_empty_workbook(client):
    r = upload(client, "empty.xlsx", workbook(A=pd.DataFrame()))
    assert r.status_code == 400
    assert "empty" in r.json()["detail"]

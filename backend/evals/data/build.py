"""Regenerates the eval workbook and ticket log. Seeded, so the output (and
every gold answer in cases.yaml) only changes if this script changes.

    python -m evals.data.build
"""
import os
import random
from datetime import date, timedelta
import pandas as pd

HERE = os.path.dirname(__file__)

def store(rng: random.Random):
    cities = ["Delhi", "Mumbai", "Pune", "Bengaluru", "Chennai"]
    segments = ["Retail", "Wholesale"]
    customers = pd.DataFrame({
        "customer_id": range(1, 21),
        "name": [f"Customer {i:02d}" for i in range(1, 21)],
        "city": [cities[i % 5] for i in range(20)],
        "segment": [segments[i % 3 == 0] for i in range(20)],
    })
    products = pd.DataFrame({
        "product_id": range(101, 109),
        "product": ["Notebook", "Pen Pack", "Stapler", "Desk Lamp", "Backpack", "Water Bottle", "Calculator", "Planner"],
        "category": ["Stationery", "Stationery", "Stationery", "Home", "Bags", "Home", "Electronics", "Stationery"],
        "price": [120.0, 45.0, 230.0, 899.0, 1499.0, 349.0, 650.0, 275.0],
    })
    start = date(2024, 1, 1)
    orders = pd.DataFrame({
        "order_id": range(5001, 5121),
        "customer_id": [rng.randint(1, 20) for _ in range(120)],
        "product_id": [rng.randint(101, 108) for _ in range(120)],
        "order_date": [start + timedelta(days=rng.randint(0, 180)) for _ in range(120)],
        "qty": [rng.randint(1, 6) for _ in range(120)],
    }).sort_values("order_date", kind="stable").reset_index(drop=True)
    orders["order_date"] = pd.to_datetime(orders["order_date"])

    with pd.ExcelWriter(os.path.join(HERE, "store.xlsx")) as xl:
        orders.to_excel(xl, sheet_name="Orders", index=False)
        customers.to_excel(xl, sheet_name="Customers", index=False)
        products.to_excel(xl, sheet_name="Products", index=False)

def tickets(rng: random.Random):
    # deliberately cryptic headers — the column notes in cases.yaml explain them
    rows = []
    start = date(2024, 3, 1)
    for i in range(1, 81):
        opened = start + timedelta(days=rng.randint(0, 60))
        st = rng.choices(["O", "R", "X"], weights=[2, 7, 1])[0]
        rows.append({
            "tkt": f"T{i:04d}",
            "opened": opened,
            "closed": opened + timedelta(days=rng.randint(0, 9)) if st == "R" else None,
            "pri": rng.choices([1, 2, 3, 4], weights=[1, 3, 4, 2])[0],
            "st": st,
            "agt": rng.choice(["asha", "bilal", "chen", "dev"]),
            "csat": rng.randint(1, 5) if st == "R" and rng.random() < 0.7 else None,
        })
    df = pd.DataFrame(rows)
    df["csat"] = df["csat"].astype("Int64")
    df.to_csv(os.path.join(HERE, "tickets.csv"), index=False)

if __name__ == "__main__":
    store(random.Random(7))
    tickets(random.Random(11))
    print("wrote store.xlsx and tickets.csv")

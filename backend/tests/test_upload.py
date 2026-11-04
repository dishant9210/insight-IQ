import io, os
from datetime import datetime, timedelta, timezone
import pandas as pd
from app.db import SessionLocal, Dataset, UPLOAD_DIR
from app.services import dataset_service
from tests.conftest import upload

def test_csv_upload(sales):
    assert sales["status"] == "ready"
    assert sales["rows"] == 4
    assert sales["columns"] == ["name", "amount", "when"]
    assert sales["detected_types"]["when"] == "datetime"
    assert sales["preview"][1]["amount"] is None, "NaN should serialise as null"
    assert [t["name"] for t in sales["tables"]] == ["data"]

def test_dataset_is_stored_in_the_database(client, sales):
    with SessionLocal() as s:
        ds = s.get(Dataset, sales["dataset_id"])
    assert ds.status == "ready" and ds.filename == "sales.csv" and ds.rows == 4
    r = client.get(f"/api/datasets/{sales['dataset_id']}")
    assert r.status_code == 200 and r.json()["columns"] == sales["columns"]

def test_parquet_upload(client):
    buf = io.BytesIO()
    pd.DataFrame({"a": [1, 2], "b": ["x", None]}).to_parquet(buf)
    r = upload(client, "t.parquet", buf.getvalue())
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == 2

def test_oversized_upload_is_rejected_and_removed(client):
    r = upload(client, "big.csv", "a\n" + "1\n" * 600_000, "text/csv")
    assert r.status_code == 413
    assert not [f for f in os.listdir(UPLOAD_DIR) if f.endswith(".csv")], "raw upload left behind"

def test_unsupported_and_missing_extension(client):
    assert upload(client, "x.txt", "hi", "text/plain").status_code == 400
    assert upload(client, "noext", "hi", "text/plain").status_code == 400

def test_unparseable_file_fails_cleanly(client):
    r = upload(client, "broken.xlsx", b"not really excel")
    assert r.status_code == 400
    assert "Could not parse file" in r.json()["detail"]
    with SessionLocal() as s:
        assert s.query(Dataset).one().status == "failed"

def test_ids_that_are_not_uuids_never_touch_the_filesystem(client):
    for bad in ["../../etc/passwd", "x", "38e2140d-3290-43de-991d-f815b9df25f3.json"]:
        assert client.get(f"/api/datasets/{bad}").status_code == 404, bad

def test_ttl_cleanup(client, sales, monkeypatch):
    fresh = upload(client, "fresh.csv", "a\n1\n", "text/csv").json()["dataset_id"]
    old = sales["dataset_id"]
    with SessionLocal() as s:
        s.get(Dataset, old).created_at = datetime.now(timezone.utc) - timedelta(hours=3)
        s.commit()

    monkeypatch.setattr(dataset_service, "DATASET_TTL", 2 * 3600)
    dataset_service.cleanup_old()

    assert client.get(f"/api/datasets/{old}").status_code == 404
    assert not os.path.exists(dataset_service._db_path(old))
    assert client.get(f"/api/datasets/{fresh}").status_code == 200

def test_ready_without_redis(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"
    assert r.json()["queue"].startswith("disabled")

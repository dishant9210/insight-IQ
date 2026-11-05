"""Moving rows from an old SQLite file into the configured database."""
from datetime import datetime, timedelta
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from app import copy_db
from app.db import Base, SessionLocal, Dataset, QueryLog, RefreshToken, User

def old_database(tmp_path) -> str:
    url = f"sqlite:///{tmp_path}/old.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    now = datetime(2026, 11, 1, 12, 0)
    with Session(engine) as s:
        s.add(User(id="u1", email="old@example.com", password_hash="$argon2id$x", created_at=now))
        s.add(RefreshToken(id=7, user_id="u1", family="f", token_hash="h" * 64,
                           expires_at=now + timedelta(days=30), created_at=now))
        s.add(Dataset(id="d1", owner_id="u1", filename="a.csv", status="ready", rows=2,
                      warnings=[], created_at=now, updated_at=now))
        s.add(QueryLog(id=41, dataset_id="d1", user_id="u1", question="total?", sql="SELECT 1",
                       status="ok", latency_ms=5, schema_hash="abc", embedding=[0.5] * 384,
                       embedder="hash", created_at=now))
        s.commit()
    engine.dispose()
    return url

def test_copies_every_table(tmp_path):
    copied = copy_db.copy(old_database(tmp_path))
    assert copied == {"users": 1, "datasets": 1, "query_log": 1, "refresh_tokens": 1}
    with SessionLocal() as s:
        assert s.get(User, "u1").email == "old@example.com"
        assert s.get(Dataset, "d1").owner_id == "u1"
        row = s.get(QueryLog, 41)
        assert row.question == "total?" and row.embedding[:2] == [0.5, 0.5]

def test_running_twice_is_harmless(tmp_path):
    url = old_database(tmp_path)
    copy_db.copy(url)
    assert set(copy_db.copy(url).values()) == {0}

def test_new_rows_get_fresh_ids_after_a_copy(tmp_path):
    copy_db.copy(old_database(tmp_path))
    with SessionLocal() as s:
        s.add(QueryLog(dataset_id="d1", question="next", status="ok", latency_ms=1))
        s.commit()
        assert s.scalar(select(func.max(QueryLog.id))) > 41

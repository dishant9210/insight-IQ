import os, sys, tempfile

# Configure before anything from app/ is imported — settings are read at import time.
_tmp = tempfile.mkdtemp(prefix="insightiq-tests-")
os.environ["UPLOAD_DIR"] = _tmp
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")   # CI overrides with Postgres
os.environ["GROQ_API_KEY"] = "test-key"
os.environ["MAX_UPLOAD_MB"] = "1"
os.environ.pop("REDIS_URL", None)
os.environ["EMBEDDER"] = "hash"           # no model download in tests
os.environ["METRICS_PORT"] = "0"          # no metrics server; tests read the registry directly
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-hs256"
os.environ["COOKIE_SECURE"] = "false"     # the test client talks plain http
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db import SessionLocal, Dataset, QueryLog, RefreshToken, User
from app.main import app
from app.services import llm_service
from app import store

BACKEND = os.path.dirname(os.path.dirname(__file__))

@pytest.fixture(scope="session", autouse=True)
def migrated():
    # run the real migrations, so a broken migration fails the suite
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "migrations"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

@pytest.fixture(autouse=True)
def clean_db():
    yield
    with SessionLocal() as s:
        s.execute(delete(QueryLog))
        s.execute(delete(Dataset))
        s.execute(delete(RefreshToken))
        s.execute(delete(User))
        s.commit()

@pytest.fixture(autouse=True)
def fresh_store(monkeypatch):
    # every test gets an empty cache and fresh rate-limit counters
    s = store.MemoryStore()
    monkeypatch.setattr(store, "_store", s)
    return s

@pytest.fixture
def client():
    return TestClient(app)

class FakeChain:
    """Stands in for a LangChain chain: returns a fixed reply and records the inputs."""
    def __init__(self, out):
        self.out = out
        self.inputs = None

    async def ainvoke(self, inputs):
        self.inputs = inputs
        return self.out

@pytest.fixture
def fake_llm(monkeypatch):
    def install(sql, insight="insight text"):
        chain = FakeChain(sql)
        monkeypatch.setattr(llm_service, "sql_chain", chain)
        monkeypatch.setattr(llm_service, "insight_chain", FakeChain(insight))
        return chain
    return install

def upload(client, name, content, mime="application/octet-stream"):
    return client.post("/api/upload", files={"file": (name, content, mime)})

SALES_CSV = (
    "name,amount,when\n"
    "alice,10,2024-01-01\n"
    "bob,,2024-02-01\n"
    "carol,30,2024-03-01\n"
    "dave,40,2024-04-01\n"
)

@pytest.fixture
def sales(client):
    r = upload(client, "sales.csv", SALES_CSV, "text/csv")
    assert r.status_code == 200, r.text
    return r.json()

@pytest.fixture
def upload_sales(client):
    def go():
        r = upload(client, "sales.csv", SALES_CSV, "text/csv")
        assert r.status_code == 200, r.text
        return r.json()
    return go

PASSWORD = "correct horse battery"

def sign_up(client, email):
    """Register and return Authorization headers. Each user gets their own
    client so refresh cookies don't mix."""
    r = client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

@pytest.fixture
def alice():
    c = TestClient(app)
    return c, sign_up(c, "alice@example.com")

@pytest.fixture
def bob():
    c = TestClient(app)
    return c, sign_up(c, "bob@example.com")

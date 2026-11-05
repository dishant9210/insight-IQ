"""Loads the eval datasets through the real ingest path into a throwaway
workspace, so the model sees exactly the schema the api would show it."""
import os
import shutil
import tempfile
import uuid

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")

def isolate():
    """Point the app at a temp dir + SQLite and turn off Redis. Call before importing app.*"""
    tmp = tempfile.mkdtemp(prefix="insightiq-eval-")
    os.environ["UPLOAD_DIR"] = tmp
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/eval.db"
    os.environ.pop("REDIS_URL", None)
    os.environ.setdefault("EMBEDDER", "hash")
    return tmp

def load(filename: str) -> dict:
    """Ingest evals/data/<filename>; returns the dataset meta (with dataset_id)."""
    from app.db import Base, engine, SessionLocal, Dataset
    from app.services import dataset_service

    Base.metadata.create_all(engine)
    dataset_id = str(uuid.uuid4())
    ext = os.path.splitext(filename)[1]
    raw = os.path.join(os.environ["UPLOAD_DIR"], f"{dataset_id}{ext}")
    shutil.copy(os.path.join(DATA, filename), raw)
    with SessionLocal() as s:
        s.add(Dataset(id=dataset_id, filename=filename, status="pending"))
        s.commit()
    dataset_service.ingest(dataset_id, raw, filename)
    meta = dataset_service.get_ready_dataset(dataset_id)
    return meta
